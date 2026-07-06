"""
Launches a local browser with remote debugging enabled and returns a
connected CDPClient for a fresh tab.

Which browser is configurable (see BROWSERS). Every browser here today is
Chromium-family and speaks CDP, so they all share the launcher below. To add
a non-Chromium engine later (Firefox via WebDriver BiDi, WebKit inspector),
give its registry entry a different "engine" and branch on it in run_suite —
the Page interface it must satisfy is the seam, not this launcher.

Selection precedence (first that resolves wins):
  1. explicit `browser=` passed to Browser()  (from --browser or intent "browser")
  2. $OWNTEST_BROWSER
  3. "chrome"
The binary itself can always be pinned with $OWNTEST_CHROME=/path/to/exe,
which overrides the candidate search for whichever browser is selected.
"""
import asyncio
import os
import shutil
import subprocess
import tempfile

from .client import CDPClient, discover_targets

# name -> how to find and drive it. "candidates" are tried in order via PATH
# lookup then literal-path existence. All CDP entries use the shared launcher.
BROWSERS: dict[str, dict] = {
    "chrome": {
        "engine": "cdp",
        "candidates": [
            "google-chrome", "google-chrome-stable",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ],
    },
    "edge": {
        "engine": "cdp",
        "candidates": [
            "microsoft-edge", "microsoft-edge-stable",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ],
    },
    "brave": {
        "engine": "cdp",
        "candidates": [
            "brave-browser", "brave",
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        ],
    },
    "chromium": {
        "engine": "cdp",
        "candidates": [
            "chromium", "chromium-browser",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ],
    },
}

DEFAULT_BROWSER = "chrome"


def resolve_browser(browser: str | None) -> str:
    """Apply the selection precedence and validate the name."""
    name = browser or os.environ.get("OWNTEST_BROWSER") or DEFAULT_BROWSER
    if name not in BROWSERS:
        raise RuntimeError(
            f"Unknown browser {name!r}. Available: {', '.join(BROWSERS)}"
        )
    return name


def find_browser_binary(browser: str | None = None) -> str:
    """Locate the executable for the selected browser."""
    name = resolve_browser(browser)
    override = os.environ.get("OWNTEST_CHROME", "")  # pins the binary if set
    for c in [override, *BROWSERS[name]["candidates"]]:
        if not c:
            continue
        path = shutil.which(c) or (c if os.path.exists(c) else None)
        if path:
            return path
    raise RuntimeError(
        f"No binary found for browser {name!r}. Install it, pick another with "
        f"OWNTEST_BROWSER / --browser, or set OWNTEST_CHROME=/path/to/exe."
    )


class Browser:
    def __init__(self, headless: bool = True, port: int = 9222,
                 browser: str | None = None):
        self.headless = headless
        self.port = port
        self.name = resolve_browser(browser)
        self.proc: subprocess.Popen | None = None
        self.user_data_dir = tempfile.mkdtemp(prefix="owntest-profile-")

    async def start(self) -> "Browser":
        binary = find_browser_binary(self.name)
        args = [
            binary,
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.user_data_dir}",
            "--no-first-run", "--no-default-browser-check",
            "--disable-background-networking", "--disable-sync",
        ]
        if self.headless:
            args.append("--headless=new")
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # wait for the debugging endpoint to come up
        for _ in range(50):
            try:
                targets = await discover_targets(port=self.port)
                if targets:
                    return self
            except Exception:
                pass
            await asyncio.sleep(0.2)
        raise RuntimeError(
            f"{self.name} started but its debugging endpoint never became reachable"
        )

    async def new_page_client(self) -> CDPClient:
        targets = await discover_targets(port=self.port)
        page = next((t for t in targets if t.get("type") == "page"), None)
        if page is None:
            raise RuntimeError("No page target found")
        client = CDPClient(page["webSocketDebuggerUrl"])
        await client.connect()
        # enable the domains our Page layer relies on
        for domain in ("Page", "Runtime", "DOM", "Network"):
            await client.send(f"{domain}.enable")
        return client

    async def stop(self):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
