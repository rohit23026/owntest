"""
OwnTest CDP Client
Raw Chrome DevTools Protocol client over WebSocket.
No Playwright, no Selenium — this IS your execution engine's core.

Chrome must be started with: --remote-debugging-port=<port>
"""
import asyncio
import itertools
import json
import urllib.request

import websockets


class CDPError(Exception):
    def __init__(self, method, error):
        self.method = method
        self.error = error
        super().__init__(f"CDP {method} failed: {error}")


class CDPClient:
    """One WebSocket connection to a single browser target (tab)."""

    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self._ws = None
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}
        self._event_handlers: dict[str, list] = {}
        self._listen_task = None

    async def connect(self):
        self._ws = await websockets.connect(self.ws_url, max_size=50 * 1024 * 1024)
        self._listen_task = asyncio.create_task(self._listen())
        return self

    async def _listen(self):
        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                if "id" in msg:                      # response to a command
                    fut = self._pending.pop(msg["id"], None)
                    if fut and not fut.done():
                        if "error" in msg:
                            fut.set_exception(CDPError(msg.get("method", "?"), msg["error"]))
                        else:
                            fut.set_result(msg.get("result", {}))
                elif "method" in msg:                # event
                    for handler in self._event_handlers.get(msg["method"], []):
                        handler(msg.get("params", {}))
        except websockets.ConnectionClosed:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(ConnectionError("CDP connection closed"))

    async def send(self, method: str, params: dict | None = None, timeout: float = 30.0):
        """Send a CDP command and await its result."""
        msg_id = next(self._ids)
        fut = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = fut
        await self._ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise CDPError(method, {"message": f"timed out after {timeout}s"})

    def on(self, event: str, handler):
        """Subscribe to a CDP event, e.g. 'Page.loadEventFired'."""
        self._event_handlers.setdefault(event, []).append(handler)

    async def wait_for_event(self, event: str, timeout: float = 30.0):
        fut = asyncio.get_event_loop().create_future()

        def once(params):
            if not fut.done():
                fut.set_result(params)

        self.on(event, once)
        return await asyncio.wait_for(fut, timeout)

    async def close(self):
        if self._listen_task:
            self._listen_task.cancel()
        if self._ws:
            await self._ws.close()


async def discover_targets(host: str = "127.0.0.1", port: int = 9222) -> list[dict]:
    """List debuggable targets from Chrome's HTTP endpoint."""
    def _fetch():
        with urllib.request.urlopen(f"http://{host}:{port}/json/list", timeout=5) as r:
            return json.loads(r.read())
    return await asyncio.get_event_loop().run_in_executor(None, _fetch)


async def open_new_tab(host: str = "127.0.0.1", port: int = 9222, url: str = "about:blank") -> dict:
    def _fetch():
        req = urllib.request.Request(f"http://{host}:{port}/json/new?{urllib.parse.urlencode({'url': url})}",
                                     method="PUT")
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    import urllib.parse
    return await asyncio.get_event_loop().run_in_executor(None, _fetch)
