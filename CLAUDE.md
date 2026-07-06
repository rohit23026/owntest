# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Intent Automation (branding; the Python package and env vars keep the original name
`owntest`/`OWNTEST_*`) is a test automation engine built from scratch, deliberately avoiding existing
frameworks: raw Chrome DevTools Protocol instead of Playwright/Selenium, a stdlib HTTP
client instead of requests/Postman, and a provider-agnostic LLM layer instead of binding
to one vendor SDK. The point of the project is to own every layer, not to wrap an
existing tool.

Everything flows through one contract, **Test Intent JSON**:

```
Jira/GitHub requirement ──► LLM layer ──► Test Intent JSON ──► Runner ──► Report
                              ▲                                  │
                   real context: OpenAPI chunks,          ┌──────┴──────┐
                   page_map from the UI engine            ▼             ▼
                                                      API engine    UI engine (CDP)
```

The LLM's only job is producing Test Intent JSON from a requirement + real context
(OpenAPI spec chunk, `page_map()` snapshot). It never invents endpoints or selectors —
`generate_test_intent()` in [owntest/llm/provider.py](owntest/llm/provider.py) schema-validates
output before it ever reaches an engine, since LLM output is treated as untrusted input.

## Commands

```bash
pip install -r requirements.txt

# run the fake target API used by the example intent
python3 tests/demo_server.py &

# run a suite (API tests need no browser; UI tests need local Chrome)
python3 -m owntest.runner examples/orders_api_intent.json
python3 -m owntest.runner my_intent.json --headed        # watch UI tests run
python3 -m owntest.runner my_intent.json --browser edge  # chrome|edge|brave|chromium
python3 -m owntest.runner my_intent.json --env staging   # resolves {{category.key}} variables
python3 -m owntest.runner my_intent.json --api-base-url http://host:port

# The app (Flask server + static UI)
python app/server.py                 # browser UI at http://127.0.0.1:8700
python app/desktop.py                # native WebView2 window, same server
```

Exit code from `owntest.runner` is 0 iff every test passed — this is what CI depends on.

There is currently no automated test suite (no pytest/unittest files) and no lint config
in the repo. [tests/demo_server.py](tests/demo_server.py) is a fixture (a fake orders API), not a test file.
UI tests default to Chrome; pick another Chromium browser with `--browser`
(`chrome|edge|brave|chromium`), the `OWNTEST_BROWSER` env var, or a `"browser"`
field in the intent. If the binary isn't auto-detected, pin it with
`OWNTEST_CHROME=/path/to/exe`. The registry lives in [owntest/cdp/browser.py](owntest/cdp/browser.py).
LLM generation needs `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in the environment.

### Building the Windows installer
```bash
pip install -r requirements.txt pyinstaller
pyinstaller build/owntest.spec
# optional: install Inno Setup, drop MicrosoftEdgeWebview2Setup.exe into build/, then
iscc build\installer.iss    # -> dist/IntentAutomation-Setup.exe
```
`.github/workflows/build.yml` does this automatically on push (Windows runner, PyInstaller
+ Inno Setup) — download `IntentAutomation-Setup` / `IntentAutomation-portable` artifacts from Actions.

## Architecture

```
owntest/
  cdp/client.py    raw CDP WebSocket client (commands, events, timeouts)
  cdp/browser.py   Chrome launcher + target discovery
  ui/page.py       goto/click/type/waits/asserts/screenshots + page_map() for the LLM
  api/engine.py    HTTP client + assertions (status, json_path, header, body, latency)
  llm/provider.py  LLMProvider ABC + Anthropic/OpenAI adapters + generate_test_intent()
  config_store.py  environments + variables (SQLite in the user data dir)
  runner.py        suite orchestration, JSON report, CI exit codes
app/server.py      Flask app powering both the browser UI and the desktop window
app/desktop.py     entry point that starts server.py and opens a native WebView2 window
```

**Test Intent schema** (the contract everything speaks — see the docstring at the top of
[owntest/runner.py](owntest/runner.py) for the full example): a suite is a JSON document with
`suite`, `requirement_ref` (traces back to Jira/GitHub), and a `tests` list where each test
is `type: "api"` (a `request` + `assertions`) or `type: "ui"` (a list of `steps`). The LLM
system prompt, the runner's action/assertion dispatch, and any UI editor must all agree on
this schema if it changes.

Any string field may reference environment variables as `{{category.key}}` (e.g.
`{{api.base_url}}`, categories: ui/api/kafka/db). [owntest/config_store.py](owntest/config_store.py)
stores them in SQLite (`config.db` in the user data dir, edited via the app's ⚙ page)
and `run_suite(env=...)` resolves them before execution — failing loud on undefined
variables or a missing environment, never running with a literal placeholder.

Data-driven testing: a test may carry a `"data"` list of row objects; the runner
(`_expand_data`) runs the test once per row, resolving `{{data.column}}` placeholders
(a string that is exactly one placeholder keeps the row value's type, so numbers
survive into JSON bodies). Each iteration reports separately as `id [2/4]`.
`{{data.*}}` is reserved — environment substitution never touches it.

The app's main page is table-driven (no JSON editing needed): a pack dropdown
(ui/api/kafka/db) selects the pack, each test opens editable step/request/assertion
tables plus its data table (`{ }` button shows the raw document). Per-test ▶ runs a
single test. There is no file picker — the app keeps exactly one intent document per
pack (`<pack>.json` in the user data dir's `intents/`), seeded on first run from the
bundled examples (tests merged by type) and from default-env config values
(`api.base_url` → the demo API) so the examples run out of the box. The CLI still
runs any intent file directly, including the pack files.

**CDP layer is the actual browser automation engine**, not a wrapper around one:
- [owntest/cdp/client.py](owntest/cdp/client.py) — one WebSocket per tab, request/response
  correlation by message id, event subscription (`on()` / `wait_for_event()`).
- [owntest/cdp/browser.py](owntest/cdp/browser.py) — launches Chrome with
  `--remote-debugging-port`, uses `Page`/`Runtime`/`DOM`/`Network` domains.
- [owntest/ui/page.py](owntest/ui/page.py) — interactions are split deliberately: reads/asserts
  go through `Runtime.evaluate` (JS in the page), but clicks/typing go through
  `Input.dispatchMouseEvent` / `Input.insertText` (real trusted input events) rather than
  JS injection, so it behaves like an actual user. `page_map()` here is what feeds the LLM
  real, existing selectors so it can't hallucinate.

**API engine** ([owntest/api/engine.py](owntest/api/engine.py)) is pure `http.client`, no
`requests`. Adding a new assertion type means adding a branch in `run_assertions()` and
updating the schema comment.

**LLM layer** ([owntest/llm/provider.py](owntest/llm/provider.py)) is provider-agnostic by
design: business logic depends on the `LLMProvider` ABC (`complete(system, user) -> str`),
never on a vendor SDK directly. `AnthropicProvider` and `OpenAIProvider` both hit their APIs
with raw `urllib.request` (no SDK dependency); `OpenAIProvider`'s `base_url` makes it work
against any OpenAI-compatible endpoint (Azure, Ollama, vLLM). New providers register in
the `PROVIDERS` dict and are selected via `OWNTEST_LLM` env var or `get_provider(name)`.

**Runner** ([owntest/runner.py](owntest/runner.py)) runs API tests synchronously first, then
starts a browser only if the suite has UI tests, running them all through one shared `Page`
before tearing the browser down. Report is a single JSON dict with per-test pass/fail,
timing, and per-assertion detail — this is what both the CLI and `app/server.py`'s
`/api/run` endpoint return.

**app/server.py** is the single Flask app behind both delivery modes (browser and desktop
window via `app/desktop.py` + pywebview). It's frozen-app aware: `sys.frozen` and
`sys._MEIPASS` detect running inside the PyInstaller `.exe`, and user data (intents,
reports) is deliberately kept out of the install directory — it lives under `%APPDATA%\OwnTest`
(or `~/.owntest`) since Program Files is read-only. On first run it seeds that directory
from the bundled `examples/`. Runs execute in a background thread and are polled via
`/api/run/<run_id>`, not returned synchronously. `POST /api/run/<run_id>/stop` requests
cooperative cancellation: the runner checks between tests/iterations (never mid-step),
finishes the current test, and returns a partial report with `"stopped": true`.

## Known gaps (relevant when extending the UI engine)

- Chromium-only engine (CDP) — Chrome/Edge/Brave/Chromium are selectable, but
  no Firefox/WebKit yet (would need a non-CDP engine behind the same `Page` seam).
- No iframe/shadow-DOM traversal, no file-upload/drag-drop, single tab only.
- Auto-wait (`Page.wait_for`) is 100ms polling, not MutationObserver-based.
- No test isolation / setup-teardown hooks in the intent schema yet — a real bug was hit
  in the first demo run where leftover state broke a list assertion.

See the README's Roadmap section for planned work (self-healing selectors, Jira/GitHub
connectors, failure classifier, network mocking via CDP `Fetch`, a Kafka engine).
