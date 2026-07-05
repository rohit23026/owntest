"""
OwnTest LLM Layer — provider-agnostic.
"Attach to any LLM" = one interface, many adapters. Business logic never
imports a vendor SDK directly.

The LLM's ONLY job: requirement text + real context (OpenAPI spec chunk,
page_map from the UI engine) -> Test Intent JSON. The engines do the rest.
"""
import json
import os
import urllib.request
from abc import ABC, abstractmethod

SYSTEM_PROMPT = """You are a test generation engine. You convert software requirements
into Test Intent JSON for the OwnTest runner. Respond with ONLY valid JSON, no prose,
no markdown fences.

Rules:
- Only reference API endpoints that appear in the provided OpenAPI context.
- Only reference UI selectors derivable from the provided page_map (prefer
  data-testid, then id, then role/name). Never invent selectors.
- Every test must trace to the requirement via "requirement_ref".
- Include negative and boundary tests for API endpoints where the schema allows.

Output schema:
{"suite": str, "requirement_ref": str, "api_base_url": str, "tests": [
  {"id": str, "type": "api", "request": {"method": str, "path": str, "json": obj?,
   "params": obj?, "headers": obj?},
   "assertions": [{"type": "status|json_path|header|body_contains|max_ms", ...}]},
  {"id": str, "type": "ui", "steps": [
   {"action": "goto|click|type|wait_for|assert_text|assert_url|screenshot", ...}]}
]}"""


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, system: str, user: str) -> str: ...


class AnthropicProvider(LLMProvider):
    def __init__(self, model: str = "claude-sonnet-4-6", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]

    def complete(self, system: str, user: str) -> str:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            method="POST",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            data=json.dumps({
                "model": self.model,
                "max_tokens": 4096,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            }).encode(),
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
        return "".join(b["text"] for b in data["content"] if b["type"] == "text")


class OpenAIProvider(LLMProvider):
    def __init__(self, model: str = "gpt-4o", api_key: str | None = None,
                 base_url: str = "https://api.openai.com/v1"):
        self.model = model
        self.api_key = api_key or os.environ["OPENAI_API_KEY"]
        self.base_url = base_url  # point at any OpenAI-compatible endpoint
                                  # (Azure, Ollama, vLLM, etc.)

    def complete(self, system: str, user: str) -> str:
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            method="POST",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "content-type": "application/json"},
            data=json.dumps({
                "model": self.model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
            }).encode(),
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
        return data["choices"][0]["message"]["content"]


PROVIDERS = {"anthropic": AnthropicProvider, "openai": OpenAIProvider}


def get_provider(name: str | None = None, **kwargs) -> LLMProvider:
    name = name or os.environ.get("OWNTEST_LLM", "anthropic")
    return PROVIDERS[name](**kwargs)


def _extract_json(text: str) -> dict:
    """Tolerate models that wrap output in fences despite instructions."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


def generate_test_intent(requirement: str,
                         openapi_context: str = "",
                         page_map: list | None = None,
                         requirement_ref: str = "",
                         provider: LLMProvider | None = None) -> dict:
    """
    The single entry point your Jira/GitHub connectors call.
    Feed it REAL context (spec chunks, page_map) or the model will hallucinate.
    """
    provider = provider or get_provider()
    user = f"REQUIREMENT (ref: {requirement_ref}):\n{requirement}\n"
    if openapi_context:
        user += f"\nOPENAPI CONTEXT:\n{openapi_context}\n"
    if page_map:
        user += f"\nPAGE MAP (real elements on the page):\n{json.dumps(page_map, indent=1)}\n"

    raw = provider.complete(SYSTEM_PROMPT, user)
    intent = _extract_json(raw)

    # Validate before it ever touches an engine — LLM output is untrusted input.
    assert isinstance(intent.get("tests"), list) and intent["tests"], "no tests generated"
    for t in intent["tests"]:
        assert t.get("type") in ("api", "ui"), f"bad test type: {t.get('type')}"
        if t["type"] == "api":
            assert "request" in t and "method" in t["request"], "api test missing request"
        else:
            assert isinstance(t.get("steps"), list) and t["steps"], "ui test missing steps"
    intent.setdefault("requirement_ref", requirement_ref)
    return intent
