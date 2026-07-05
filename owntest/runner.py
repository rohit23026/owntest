"""
OwnTest Runner — executes Test Intent documents.

TEST INTENT is the contract of your whole product. Your LLM layer emits it,
your engines consume it, your reports read it. Example:

{
  "suite": "checkout",
  "requirement_ref": "JIRA-123",           // traceability back to Jira/GitHub
  "tests": [
    {
      "id": "api-create-order",
      "type": "api",
      "request": {"method": "POST", "path": "/orders",
                  "json": {"sku": "ABC", "qty": 2}},
      "assertions": [
        {"type": "status", "equals": 201},
        {"type": "json_path", "path": "order.qty", "equals": 2}
      ]
    },
    {
      "id": "ui-login",
      "type": "ui",
      "steps": [
        {"action": "goto",  "url": "https://app.example.com/login"},
        {"action": "type",  "selector": "#email", "text": "a@b.com"},
        {"action": "type",  "selector": "#password", "text": "secret"},
        {"action": "click", "selector": "button[type=submit]"},
        {"action": "assert_text", "selector": "h1", "contains": "Dashboard"},
        {"action": "assert_url", "contains": "/dashboard"},
        {"action": "screenshot", "path": "evidence/login.png"}
      ]
    }
  ]
}
"""
import asyncio
import json
import time
from dataclasses import dataclass, field

from .api.engine import HttpEngine, run_assertions


@dataclass
class TestResult:
    test_id: str
    test_type: str
    passed: bool
    duration_ms: float
    checks: list = field(default_factory=list)
    error: str = ""


# ---------------- API execution ----------------
def run_api_test(test: dict, engine: HttpEngine) -> TestResult:
    start = time.perf_counter()
    try:
        req = test["request"]
        resp = engine.request(
            req["method"], req["path"],
            headers=req.get("headers"),
            json_body=req.get("json"),
            params=req.get("params"),
        )
        checks = run_assertions(resp, test.get("assertions", []))
        return TestResult(
            test_id=test["id"], test_type="api",
            passed=all(c.passed for c in checks),
            duration_ms=round((time.perf_counter() - start) * 1000, 1),
            checks=[c.__dict__ for c in checks],
        )
    except Exception as e:
        return TestResult(test["id"], "api", False,
                          round((time.perf_counter() - start) * 1000, 1),
                          error=str(e))


# ---------------- UI execution ----------------
async def run_ui_test(test: dict, page) -> TestResult:
    from .ui.page import ElementNotFound  # noqa
    start = time.perf_counter()
    checks = []
    try:
        for step in test["steps"]:
            act = step["action"]
            if act == "goto":
                await page.goto(step["url"])
            elif act == "click":
                await page.click(step["selector"])
            elif act == "type":
                await page.type(step["selector"], step["text"])
            elif act == "wait_for":
                await page.wait_for(step["selector"], step.get("timeout", 10))
            elif act == "assert_text":
                text = await page.text_of(step["selector"])
                ok = step["contains"] in text
                checks.append({"description": f"text of {step['selector']} contains {step['contains']!r}",
                               "passed": ok, "detail": f"got {text!r}"})
                if not ok:
                    raise AssertionError(checks[-1]["description"])
            elif act == "assert_url":
                url = await page.url()
                ok = step["contains"] in url
                checks.append({"description": f"url contains {step['contains']!r}",
                               "passed": ok, "detail": f"got {url!r}"})
                if not ok:
                    raise AssertionError(checks[-1]["description"])
            elif act == "screenshot":
                await page.screenshot(step["path"])
            else:
                raise ValueError(f"unknown UI action: {act}")
        return TestResult(test["id"], "ui", True,
                          round((time.perf_counter() - start) * 1000, 1), checks)
    except Exception as e:
        return TestResult(test["id"], "ui",
                          False,
                          round((time.perf_counter() - start) * 1000, 1),
                          checks, error=str(e))


# ---------------- Suite orchestration ----------------
async def run_suite(intent: dict, api_base_url: str = "",
                    headless: bool = True) -> dict:
    api_engine = HttpEngine(base_url=api_base_url or intent.get("api_base_url", ""))
    results: list[TestResult] = []

    ui_tests = [t for t in intent["tests"] if t["type"] == "ui"]
    api_tests = [t for t in intent["tests"] if t["type"] == "api"]

    for t in api_tests:
        results.append(run_api_test(t, api_engine))

    if ui_tests:
        from .cdp.browser import Browser
        from .ui.page import Page
        browser = await Browser(headless=headless).start()
        try:
            client = await browser.new_page_client()
            page = Page(client)
            for t in ui_tests:
                results.append(await run_ui_test(t, page))
            await client.close()
        finally:
            await browser.stop()

    passed = sum(1 for r in results if r.passed)
    return {
        "suite": intent.get("suite", "unnamed"),
        "requirement_ref": intent.get("requirement_ref"),
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": [r.__dict__ for r in results],
    }


def main():
    import argparse
    p = argparse.ArgumentParser(description="Intent Automation runner")
    p.add_argument("intent_file", help="path to test-intent JSON")
    p.add_argument("--api-base-url", default="")
    p.add_argument("--headed", action="store_true")
    args = p.parse_args()

    with open(args.intent_file) as f:
        intent = json.load(f)

    report = asyncio.run(run_suite(intent, args.api_base_url, headless=not args.headed))
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
