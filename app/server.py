"""
OwnTest Studio server.
Same server powers both the browser UI (http://127.0.0.1:8700)
and the native Windows window (app/desktop.py).
"""
import asyncio
import json
import os
import shutil
import socket
import sys
import threading
import time
import uuid

from flask import Flask, jsonify, request, send_from_directory

FROZEN = getattr(sys, "frozen", False)          # True inside the PyInstaller .exe

if FROZEN:
    RESOURCES = sys._MEIPASS                    # bundled read-only assets
else:
    RESOURCES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if RESOURCES not in sys.path:               # so `owntest` imports in dev mode
        sys.path.insert(0, RESOURCES)

# User data must NEVER live next to the .exe (Program Files is read-only).
# It lives in a per-user, writable location instead.
if os.name == "nt":
    DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "OwnTest")
else:
    DATA_DIR = os.path.join(os.path.expanduser("~"), ".owntest")

EXAMPLES_DIR = os.path.join(DATA_DIR, "intents")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")
os.makedirs(EXAMPLES_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

# First run: seed the user's intents folder with the bundled examples
_bundled_examples = os.path.join(RESOURCES, "examples")
if os.path.isdir(_bundled_examples) and not os.listdir(EXAMPLES_DIR):
    for f in os.listdir(_bundled_examples):
        if f.endswith(".json"):
            shutil.copy(os.path.join(_bundled_examples, f), EXAMPLES_DIR)


def pick_port(preferred: int = 8700) -> int:
    """Use the preferred port; if something else has it, grab any free one."""
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


app = Flask(__name__,
            static_folder=os.path.join(RESOURCES, "app", "static"),
            static_url_path="")

RUNS: dict[str, dict] = {}          # run_id -> {status, report, started}


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ---------- intent files ----------
@app.get("/api/intents")
def list_intents():
    files = [f for f in os.listdir(EXAMPLES_DIR) if f.endswith(".json")]
    return jsonify(sorted(files))


@app.get("/api/intent/<name>")
def get_intent(name):
    path = os.path.join(EXAMPLES_DIR, os.path.basename(name))
    if not os.path.exists(path):
        return jsonify({"error": "not found"}), 404
    with open(path) as f:
        return jsonify(json.load(f))


@app.post("/api/intent/<name>")
def save_intent(name):
    body = request.get_json(force=True)
    path = os.path.join(EXAMPLES_DIR, os.path.basename(name))
    with open(path, "w") as f:
        json.dump(body, f, indent=2)
    return jsonify({"saved": name})


# ---------- run execution ----------
def _execute(run_id: str, intent: dict, headed: bool):
    from owntest.runner import run_suite
    try:
        report = asyncio.run(run_suite(intent, headless=not headed))
        RUNS[run_id].update(status="done", report=report)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        with open(os.path.join(REPORTS_DIR, f"{stamp}-{report['suite']}.json"), "w") as f:
            json.dump(report, f, indent=2)
    except Exception as e:
        RUNS[run_id].update(status="error", error=str(e))


@app.post("/api/run")
def start_run():
    body = request.get_json(force=True)
    intent = body["intent"]
    run_id = uuid.uuid4().hex[:12]
    RUNS[run_id] = {"status": "running", "started": time.time(),
                    "total": len(intent.get("tests", []))}
    threading.Thread(target=_execute,
                     args=(run_id, intent, body.get("headed", False)),
                     daemon=True).start()
    return jsonify({"run_id": run_id})


@app.get("/api/run/<run_id>")
def run_status(run_id):
    run = RUNS.get(run_id)
    if not run:
        return jsonify({"error": "unknown run"}), 404
    return jsonify(run)


# ---------- LLM generation ----------
@app.post("/api/generate")
def generate():
    body = request.get_json(force=True)
    try:
        from owntest.llm.provider import generate_test_intent, get_provider
        provider = get_provider(body.get("provider"))
        intent = generate_test_intent(
            requirement=body["requirement"],
            openapi_context=body.get("openapi_context", ""),
            requirement_ref=body.get("requirement_ref", ""),
            provider=provider,
        )
        return jsonify(intent)
    except KeyError as e:
        return jsonify({"error": f"API key not set: {e}. Set ANTHROPIC_API_KEY "
                                 f"or OPENAI_API_KEY in your environment."}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def run_server(host="127.0.0.1", port=None, debug=False):
    port = port or pick_port()
    app.run(host=host, port=port, debug=debug, use_reloader=False)
    return port


if __name__ == "__main__":
    p = pick_port()
    print(f"Intent Automation Studio → http://127.0.0.1:{p}")
    run_server(port=p)
