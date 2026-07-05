"""
Intent Automation — the app end users double-click.
Starts the embedded server on a free port, opens a native window (WebView2).
Falls back to the default browser if the native window can't start.
No setup, no terminal, no Python knowledge required from the user.
"""
import threading
import time
import urllib.request
import webbrowser

from server import pick_port, run_server

PORT = pick_port()
URL = f"http://127.0.0.1:{PORT}"


def wait_until_up(timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(URL, timeout=1)
            return True
        except Exception:
            time.sleep(0.2)
    return False


if __name__ == "__main__":
    threading.Thread(target=run_server, kwargs={"port": PORT}, daemon=True).start()
    if not wait_until_up():
        raise SystemExit("Intent Automation could not start its internal server.")

    try:
        import webview
        webview.create_window("Intent Automation", URL,
                              width=1280, height=840, min_size=(980, 640))
        webview.start()
    except Exception:
        # WebView2 missing → still open, just in the default browser.
        webbrowser.open(URL)
        while True:
            time.sleep(3600)
