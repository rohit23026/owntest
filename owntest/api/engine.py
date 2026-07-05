"""
OwnTest API Engine — your own HTTP test executor.
Pure stdlib (http.client). No requests, no Postman, no REST-assured.

Assertion types supported:
  status        -> {"type":"status","equals":200}
  json_path     -> {"type":"json_path","path":"data.user.id","equals":42}
                   {"type":"json_path","path":"items","length":3}
                   {"type":"json_path","path":"name","contains":"foo"}
  header        -> {"type":"header","name":"content-type","contains":"json"}
  body_contains -> {"type":"body_contains","value":"success"}
  max_ms        -> {"type":"max_ms","value":1500}
"""
import http.client
import json
import ssl
import time
import urllib.parse
from dataclasses import dataclass, field


@dataclass
class ApiResponse:
    status: int
    headers: dict
    body: bytes
    elapsed_ms: float

    def json(self):
        return json.loads(self.body.decode("utf-8"))

    @property
    def text(self):
        return self.body.decode("utf-8", errors="replace")


@dataclass
class AssertionResult:
    description: str
    passed: bool
    detail: str = ""


class HttpEngine:
    def __init__(self, base_url: str = "", default_headers: dict | None = None,
                 timeout: float = 30.0, verify_tls: bool = True):
        self.base_url = base_url.rstrip("/")
        self.default_headers = default_headers or {}
        self.timeout = timeout
        self.verify_tls = verify_tls

    def request(self, method: str, path: str, headers: dict | None = None,
                json_body=None, body: bytes | None = None,
                params: dict | None = None) -> ApiResponse:
        url = path if path.startswith("http") else self.base_url + path
        parsed = urllib.parse.urlparse(url)
        if params:
            qs = urllib.parse.urlencode(params)
            sep = "&" if parsed.query else ""
            parsed = parsed._replace(query=parsed.query + sep + qs)

        hdrs = {**self.default_headers, **(headers or {})}
        if json_body is not None:
            body = json.dumps(json_body).encode()
            hdrs.setdefault("Content-Type", "application/json")

        if parsed.scheme == "https":
            ctx = None if self.verify_tls else ssl._create_unverified_context()
            conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443,
                                               timeout=self.timeout, context=ctx)
        else:
            conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80,
                                              timeout=self.timeout)
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query

        start = time.perf_counter()
        try:
            conn.request(method.upper(), target, body=body, headers=hdrs)
            raw = conn.getresponse()
            resp_body = raw.read()
            elapsed = (time.perf_counter() - start) * 1000
            return ApiResponse(
                status=raw.status,
                headers={k.lower(): v for k, v in raw.getheaders()},
                body=resp_body,
                elapsed_ms=round(elapsed, 1),
            )
        finally:
            conn.close()


def _json_path(data, path: str):
    """Minimal dotted-path resolver: 'data.items.0.name'."""
    cur = data
    for part in path.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            if part not in cur:
                raise KeyError(f"path segment '{part}' not found")
            cur = cur[part]
        else:
            raise KeyError(f"cannot descend into {type(cur).__name__} at '{part}'")
    return cur


def run_assertions(resp: ApiResponse, assertions: list[dict]) -> list[AssertionResult]:
    results = []
    for a in assertions:
        t = a["type"]
        try:
            if t == "status":
                ok = resp.status == a["equals"]
                results.append(AssertionResult(
                    f"status == {a['equals']}", ok, f"got {resp.status}"))
            elif t == "json_path":
                val = _json_path(resp.json(), a["path"])
                if "equals" in a:
                    ok = val == a["equals"]
                    desc = f"json {a['path']} == {a['equals']!r}"
                elif "contains" in a:
                    ok = a["contains"] in val
                    desc = f"json {a['path']} contains {a['contains']!r}"
                elif "length" in a:
                    ok = len(val) == a["length"]
                    desc = f"len(json {a['path']}) == {a['length']}"
                else:
                    ok, desc = val is not None, f"json {a['path']} exists"
                results.append(AssertionResult(desc, ok, f"got {val!r}"))
            elif t == "header":
                val = resp.headers.get(a["name"].lower(), "")
                ok = a.get("contains", "") in val
                results.append(AssertionResult(
                    f"header {a['name']} contains {a['contains']!r}", ok, f"got {val!r}"))
            elif t == "body_contains":
                ok = a["value"] in resp.text
                results.append(AssertionResult(
                    f"body contains {a['value']!r}", ok,
                    "" if ok else f"body was {resp.text[:120]!r}"))
            elif t == "max_ms":
                ok = resp.elapsed_ms <= a["value"]
                results.append(AssertionResult(
                    f"response <= {a['value']}ms", ok, f"took {resp.elapsed_ms}ms"))
            else:
                results.append(AssertionResult(f"unknown assertion '{t}'", False))
        except Exception as e:
            results.append(AssertionResult(f"{t} assertion", False, f"error: {e}"))
    return results
