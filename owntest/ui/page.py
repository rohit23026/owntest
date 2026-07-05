"""
Page — your engine's UI interaction layer, built directly on CDP.

Interactions are done two ways deliberately:
  * queries/asserts via Runtime.evaluate (JS in the page)
  * clicks/typing via Input.dispatchMouseEvent / Input.insertText
    (real trusted input events, like a human — this is what makes it a
    genuine automation engine rather than a JS injector)
"""
import asyncio
import base64
import json

from ..cdp.client import CDPClient


class ElementNotFound(Exception):
    pass


class Page:
    def __init__(self, client: CDPClient):
        self.c = client

    # ---------- navigation ----------
    async def goto(self, url: str, timeout: float = 30.0):
        load = asyncio.create_task(self.c.wait_for_event("Page.loadEventFired", timeout))
        await self.c.send("Page.navigate", {"url": url})
        await load

    # ---------- evaluate ----------
    async def eval(self, expression: str):
        res = await self.c.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        })
        if res.get("exceptionDetails"):
            raise RuntimeError(res["exceptionDetails"].get("text", "JS exception"))
        return res.get("result", {}).get("value")

    # ---------- waiting (your auto-wait strategy) ----------
    async def wait_for(self, selector: str, timeout: float = 10.0, visible: bool = True):
        js_visible = (
            "el && el.offsetParent !== null" if visible else "!!el"
        )
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            found = await self.eval(
                f"(() => {{ const el = document.querySelector({json.dumps(selector)});"
                f" return {js_visible}; }})()"
            )
            if found:
                return
            await asyncio.sleep(0.1)
        raise ElementNotFound(f"Timed out waiting for selector: {selector}")

    # ---------- element geometry ----------
    async def _center_of(self, selector: str) -> tuple[float, float]:
        box = await self.eval(
            f"(() => {{ const el = document.querySelector({json.dumps(selector)});"
            " if (!el) return null;"
            " el.scrollIntoView({block:'center', inline:'center'});"
            " const r = el.getBoundingClientRect();"
            " return {x: r.x + r.width/2, y: r.y + r.height/2}; })()"
        )
        if box is None:
            raise ElementNotFound(selector)
        return box["x"], box["y"]

    # ---------- real input events ----------
    async def click(self, selector: str, timeout: float = 10.0):
        await self.wait_for(selector, timeout)
        x, y = await self._center_of(selector)
        base = {"x": x, "y": y, "button": "left", "clickCount": 1}
        await self.c.send("Input.dispatchMouseEvent", {"type": "mouseMoved", **{k: base[k] for k in ("x", "y")}})
        await self.c.send("Input.dispatchMouseEvent", {"type": "mousePressed", **base})
        await self.c.send("Input.dispatchMouseEvent", {"type": "mouseReleased", **base})

    async def type(self, selector: str, text: str, timeout: float = 10.0):
        await self.click(selector, timeout)          # focus via real click
        await self.c.send("Input.insertText", {"text": text})

    # ---------- reads / assertions ----------
    async def text_of(self, selector: str, timeout: float = 10.0) -> str:
        await self.wait_for(selector, timeout, visible=False)
        return await self.eval(
            f"document.querySelector({json.dumps(selector)}).textContent.trim()"
        )

    async def url(self) -> str:
        return await self.eval("location.href")

    async def title(self) -> str:
        return await self.eval("document.title")

    # ---------- context extraction for your LLM layer ----------
    async def page_map(self, max_elements: int = 300) -> list[dict]:
        """
        Snapshot of interactive elements — this is what you feed to the LLM
        so it generates selectors that actually exist (kills hallucination).
        """
        return await self.eval(f"""
        (() => {{
          const els = document.querySelectorAll(
            'a,button,input,select,textarea,[role],[data-testid],[onclick]');
          const out = [];
          for (const el of els) {{
            if (out.length >= {max_elements}) break;
            out.push({{
              tag: el.tagName.toLowerCase(),
              id: el.id || null,
              testid: el.getAttribute('data-testid'),
              role: el.getAttribute('role'),
              name: el.getAttribute('name'),
              type: el.getAttribute('type'),
              text: (el.textContent || '').trim().slice(0, 80),
              placeholder: el.getAttribute('placeholder'),
              visible: el.offsetParent !== null,
            }});
          }}
          return out;
        }})()""")

    # ---------- evidence ----------
    async def screenshot(self, path: str):
        res = await self.c.send("Page.captureScreenshot", {"format": "png"})
        with open(path, "wb") as f:
            f.write(base64.b64decode(res["data"]))
