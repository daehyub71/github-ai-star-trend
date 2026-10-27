"""clients.claude — 실제 Claude 클라이언트 (FR-3.10, 결정 26).

가짜 SDK 클라이언트로 요청·응답 모양을 검증한다.

마지막 live 테스트만 실제 API 를 부른다 (`pytest -m live`, STARTREND_ANTHROPIC_API_KEY 필요, 1센트 미만).
"""

import os
from types import SimpleNamespace
from typing import Any

import pytest

from startrend.clients import claude, llm

REQ = llm.LLMRequest(system="sys", user="usr", max_tokens=512, effort="low",
                     schema={"type": "object", "properties": {}, "additionalProperties": False}, purpose="t")


class FakeCreate:
    def __init__(self, message: Any):
        self.message = message
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self.message


def message(blocks, stop="end_turn", model="claude-opus-5-5") -> SimpleNamespace:
    usage = SimpleNamespace(input_tokens=120, output_tokens=30, cache_read_input_tokens=5,
                            cache_creation_input_tokens=0)
    return SimpleNamespace(content=blocks, stop_reason=stop, usage=usage, model=model)


def fake_client(msg) -> tuple[SimpleNamespace, FakeCreate, FakeCreate]:
    beta, plain = FakeCreate(msg), FakeCreate(msg)
    return SimpleNamespace(beta=SimpleNamespace(messages=beta), messages=plain), beta, plain


def test_claude_request_uses_structured_output_effort_and_default_fallbacks():
    client, beta, plain = fake_client(message([SimpleNamespace(type="text", text="{}")]))
    claude.ClaudeLLM("k", client=client).complete(REQ)
    kw = beta.kwargs
    assert kw["model"] == "claude-opus-5-5" and kw["max_tokens"] == 512 and kw["system"] == "sys"
    assert kw["messages"] == [{"role": "user", "content": "usr"}]
    assert kw["output_config"] == {"effort": "low", "format": {"type": "json_schema", "schema": REQ.schema}}
    assert kw["fallbacks"] == "default" and kw["betas"] == [claude.FALLBACK_BETA]   # FR-3.10 ③
    assert "thinking" not in kw and "tool_choice" not in kw                        # FR-3.10 ①②
    assert plain.kwargs == {}


def test_claude_response_keeps_only_text_blocks():
    blocks = [SimpleNamespace(type="thinking", thinking="..."), SimpleNamespace(type="text", text='{"a":'),
              SimpleNamespace(type="fallback"), SimpleNamespace(type="text", text="1}")]
    client, _, _ = fake_client(message(blocks, model="claude-opus-4-8"))
    r = claude.ClaudeLLM("k", client=client).complete(REQ)
    assert r.text == '{"a":1}' and r.stop_reason == "end_turn" and r.model == "claude-opus-4-8"
    assert r.usage == llm.Usage(120, 30, 5, 0)


def test_claude_refusal_passes_through():
    client, _, _ = fake_client(message([], stop="refusal"))
    assert claude.ClaudeLLM("k", client=client).complete(REQ).stop_reason == "refusal"


def test_claude_without_fallbacks_uses_plain_messages():
    # Batch API 는 fallbacks 를 받지 않는다 — 같은 요청 모양을 일반 경로로도 만들 수 있어야 한다
    client, beta, plain = fake_client(message([SimpleNamespace(type="text", text="{}")]))
    claude.ClaudeLLM("k", client=client, fallbacks=False).complete(REQ)
    assert beta.kwargs == {} and "fallbacks" not in plain.kwargs
    assert plain.kwargs["output_config"]["effort"] == "low"


def test_claude_request_without_schema_has_no_format():
    client, beta, _ = fake_client(message([SimpleNamespace(type="text", text="hi")]))
    req = llm.LLMRequest(system="s", user="u", max_tokens=64, effort="medium")
    claude.ClaudeLLM("k", client=client).complete(req)
    assert beta.kwargs["output_config"] == {"effort": "medium"}


@pytest.mark.live
def test_claude_live_tiny_structured_call():
    key = os.environ.get("STARTREND_ANTHROPIC_API_KEY")
    if not key:
        pytest.skip("STARTREND_ANTHROPIC_API_KEY 없음")
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"],
              "additionalProperties": False}
    r = claude.ClaudeLLM(key).complete(llm.LLMRequest(system="Answer with JSON.", user="Say ok=true.",
                                                      max_tokens=256, effort="low", schema=schema))
    assert r.stop_reason == "end_turn" and '"ok"' in r.text
