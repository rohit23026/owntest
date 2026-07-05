"""A tiny fake 'orders' API to run OwnTest against. python3 tests/demo_server.py"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

ORDERS = {}
NEXT_ID = [1]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"status": "ok"})
        elif self.path == "/orders":
            self._send(200, {"orders": list(ORDERS.values())})
        elif self.path.startswith("/orders/"):
            oid = self.path.rsplit("/", 1)[1]
            if oid in ORDERS:
                self._send(200, {"order": ORDERS[oid]})
            else:
                self._send(404, {"error": "not found"})
        else:
            self._send(404, {"error": "no route"})

    def do_POST(self):
        if self.path == "/orders":
            length = int(self.headers.get("Content-Length", 0))
            try:
                payload = json.loads(self.rfile.read(length))
            except Exception:
                return self._send(400, {"error": "invalid json"})
            if "sku" not in payload or payload.get("qty", 0) <= 0:
                return self._send(422, {"error": "sku required, qty must be > 0"})
            oid = str(NEXT_ID[0]); NEXT_ID[0] += 1
            order = {"id": oid, "sku": payload["sku"], "qty": payload["qty"]}
            ORDERS[oid] = order
            self._send(201, {"order": order})
        else:
            self._send(404, {"error": "no route"})


if __name__ == "__main__":
    print("demo API on http://127.0.0.1:8077")
    HTTPServer(("127.0.0.1", 8077), Handler).serve_forever()
