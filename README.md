# Intent Automation — Your Own AI-Driven Test Automation Engine

(Engine package name: `owntest` — code imports and env vars keep that name.)

A test automation engine built from scratch:
- **UI engine**: raw Chrome DevTools Protocol (CDP) over WebSocket. No Playwright. No Selenium.
- **API engine**: own HTTP client + assertion engine. Pure Python stdlib. No Postman/REST-assured.
- **LLM layer**: provider-agnostic ("attach to any LLM") — Anthropic, OpenAI, or any
  OpenAI-compatible endpoint (Azure, Ollama, vLLM). Converts requirements → Test Intent JSON.
- **Test Intent JSON**: the single contract everything speaks. LLM emits it, engines run it,
  reports trace it back to the Jira/GitHub requirement.

```
Jira/GitHub requirement ──► LLM layer ──► Test Intent JSON ──► Runner ──► Report
                              ▲                                  │
                   real context: OpenAPI chunks,          ┌──────┴──────┐
                   page_map from the UI engine            ▼             ▼
                                                      API engine    UI engine (CDP)
```

## Layout
```
owntest/
  cdp/client.py    raw CDP WebSocket client (commands, events, timeouts)
  cdp/browser.py   Chrome launcher + target discovery
  ui/page.py       goto/click/type/waits/asserts/screenshots + page_map() for the LLM
  api/engine.py    HTTP client + assertions (status, json_path, header, body, latency)
  llm/provider.py  LLMProvider ABC + Anthropic/OpenAI adapters + generate_test_intent()
  runner.py        suite orchestration, JSON report, CI exit codes
examples/orders_api_intent.json   sample intent file
tests/demo_server.py              tiny fake API to test against
```

## Quickstart (API tests — works anywhere)
```bash
pip install websockets
python3 tests/demo_server.py &                      # demo target API
python3 -m owntest.runner examples/orders_api_intent.json
```
Exit code 0 = all passed (CI-friendly). Full JSON report on stdout.

## Quickstart (UI tests — needs local Chrome)
Add a UI test to an intent file:
```json
{"id": "ui-example", "type": "ui", "steps": [
  {"action": "goto", "url": "https://example.com"},
  {"action": "assert_text", "selector": "h1", "contains": "Example"},
  {"action": "screenshot", "path": "evidence.png"}
]}
```
```bash
python3 -m owntest.runner my_intent.json            # headless
python3 -m owntest.runner my_intent.json --headed   # watch it run
```
If Chrome isn't auto-detected: `export OWNTEST_CHROME=/path/to/chrome`

## Generate tests with an LLM
```python
from owntest.llm.provider import generate_test_intent, get_provider

intent = generate_test_intent(
    requirement="User can create an order; qty must be positive; ...",
    openapi_context=open("openapi_orders_chunk.yaml").read(),
    requirement_ref="JIRA-101",
    provider=get_provider("anthropic"),   # or "openai", or your own adapter
)
```
Feed real context (OpenAPI chunks, `Page.page_map()`) — the system prompt forbids
inventing endpoints/selectors, and output is schema-validated before execution.

## Roadmap (in order)
1. **Self-healing**: on ElementNotFound, re-run `page_map()`, fuzzy-match the intended
   element (by testid/text/role), retry, and record the healed selector.
2. **Jira/GitHub connectors**: webhook → pull requirement + acceptance criteria +
   OpenAPI spec from repo → `generate_test_intent()` → run → post results back.
3. **Failure classifier**: real bug vs stale selector vs flaky env (cheap LLM call).
4. **Test isolation**: setup/teardown hooks in intent schema (we hit this exact bug
   in the first demo run — leftover state broke a list assertion).
5. **Network layer**: request interception/mocking via CDP `Fetch` domain.
6. **Kafka engine** (v2): producer/consumer harness on confluent-kafka + schema
   registry assertions — separate engine, same Test Intent contract.

## Honest limitations (know these)
- UI engine is **Chromium-only** (CDP). Firefox/WebKit need different protocols.
- No iframe/shadow-DOM traversal yet; no file-upload/drag-drop; single tab.
- Auto-wait is polling-based (100ms); fine to start, optimize later with
  MutationObserver via `Runtime.addBinding`.
- These gaps are exactly what Playwright spent years hardening — budget for them.

## Shipping to end users (zero-setup install)
End users receive ONE file: **IntentAutomation-Setup.exe**. They double-click it, click
Next, and get a desktop icon. No Python, no pip, no terminal, no WebView2 worries
(the installer adds it silently if missing). App data (intent files, reports)
lives in %APPDATA%\OwnTest so it works even when installed to Program Files.

Two ways to produce IntentAutomation-Setup.exe (you do this once per release):
1. **Automatic (recommended)** — push this repo to GitHub. The included workflow
   (.github/workflows/build.yml) builds IntentAutomation.exe with PyInstaller and wraps it
   with Inno Setup on a Windows runner. Download the artifact from the Actions tab.
2. **Local Windows machine** —
   pip install -r requirements.txt pyinstaller
   pyinstaller build/owntest.spec
   (optional installer) install Inno Setup, drop MicrosoftEdgeWebview2Setup.exe
   into build/, then: iscc build\installer.iss → dist/IntentAutomation-Setup.exe
   dist/IntentAutomation.exe alone is also fully portable — double-click and it runs.

## Intent Automation Studio (the app)
One codebase, two doors:
- **Native Windows app**: `run_desktop.bat` (or `python app/desktop.py`) — opens the UI
  in a native WebView2 window via pywebview. No browser chrome, real desktop app feel.
- **Browser**: `run_browser.bat` (or `python app/server.py`) then open http://127.0.0.1:8700
  — same UI, usable from any browser (and later, by teammates on your network).

Studio features: intent file picker + JSON editor with live validation, one-click suite
runs with a segmented progress meter, per-test verdict rail with assertion details and
timings, "Generate from requirement" drawer (needs ANTHROPIC_API_KEY or OPENAI_API_KEY),
and every run auto-saved to `reports/` with the Jira/GitHub requirement ref.

To ship it as a single .exe later: `pyinstaller --onefile --add-data "app/static;app/static" app/desktop.py`
