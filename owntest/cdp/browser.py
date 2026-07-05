"""
Launches a local Chrome/Chromium with remote debugging enabled
and returns a connected CDPClient for a fresh tab.
"""
import asyncio
import os
import shutil
import subprocess
import tempfile

from .client import CDPClient, discover_targets

CHROME_CANDIDATES = [
    os.environ.get("OWNTEST_CHROME", ""),
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


def find_chrome() -> str:
    for c in CHROME_CANDIDATES:
        if not c:
            continue
        path = shutil.which(c) or (c if os.path.exists(c) else None)
        if path:
            return path
    raise RuntimeError(
        "No Chrome/Chromium found. Install Chrome or set OWNTEST_CHROME=/path/to/chrome"
    )


class Browser:
    def __init__(self, headless: bool = True, port: int = 9222):
        self.headless = headless
        self.port = port
        self.proc: subprocess.Popen | None = None
        self.user_data_dir = tempfile.mkdtemp(prefix="owntest-profile-")

    async def start(self) -> "Browser":
        chrome = find_chrome()
        args = [
            chrome,
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
        raise RuntimeError("Chrome started but debugging endpoint never became reachable")

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
