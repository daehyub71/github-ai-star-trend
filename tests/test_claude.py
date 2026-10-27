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


# --- Batch (FR-3.7) ---


class FakeBatches:
    def __init__(self, status: str = "ended", results: list[Any] | None = None):
        self.created: dict[str, Any] = {}
        self.status = status
        self._results = results or []
        self.asked: list[str] = []

    def create(self, **kwargs: Any) -> Any:
        self.created = kwargs
        return SimpleNamespace(id="msgbatch_01", processing_status="in_progress")

    def retrieve(self, batch_id: str) -> Any:
        self.asked.append(batch_id)
        return SimpleNamespace(id=batch_id, processing_status=self.status)

    def results(self, batch_id: str) -> Any:
        self.asked.append(batch_id)
        return iter(self._results)


def batch_client(batches: FakeBatches) -> SimpleNamespace:
    return SimpleNamespace(messages=SimpleNamespace(batches=batches))


def test_claude_batch_submit_uses_the_same_request_shape_without_fallbacks():
    fb = FakeBatches()
    bid = claude.ClaudeBatch("k", client=batch_client(fb)).submit({"r1-1": REQ})
    assert bid == "msgbatch_01"
    (only,) = fb.created["requests"]
    assert only["custom_id"] == "r1-1"
    assert only["params"] == claude.ClaudeLLM("k", client=object()).params(REQ)   # 단건과 같은 모양
    assert "fallbacks" not in only["params"] and "betas" not in fb.created       # Batch 는 fallbacks 불가


def test_claude_batch_ended_reads_processing_status():
    assert claude.ClaudeBatch("k", client=batch_client(FakeBatches("ended"))).ended("b") is True
    assert claude.ClaudeBatch("k", client=batch_client(FakeBatches("in_progress"))).ended("b") is False
    assert claude.ClaudeBatch("k", client=batch_client(FakeBatches("canceling"))).ended("b") is False


def test_claude_batch_results_map_success_refusal_and_errors():
    ok = message([SimpleNamespace(type="text", text='{"a":1}')])
    refused = message([], stop="refusal")
    err = SimpleNamespace(type="errored", error=SimpleNamespace(type="error",
                                                                error=SimpleNamespace(type="overloaded_error")))
    rows = [SimpleNamespace(custom_id="a", result=SimpleNamespace(type="succeeded", message=ok)),
            SimpleNamespace(custom_id="b", result=SimpleNamespace(type="succeeded", message=refused)),
            SimpleNamespace(custom_id="c", result=err),
            SimpleNamespace(custom_id="d", result=SimpleNamespace(type="expired"))]
    out = claude.ClaudeBatch("k", client=batch_client(FakeBatches(results=rows))).results("b")
    assert out["a"].response is not None and out["a"].response.text == '{"a":1}'
    assert out["a"].response.usage == llm.Usage(120, 30, 5, 0)
    assert out["b"].response is not None and out["b"].response.stop_reason == "refusal"
    assert out["c"].response is None and out["c"].error == "errored:overloaded_error"
    assert out["d"].response is None and out["d"].error == "expired"


def test_claude_batch_is_a_batch_client():
    b: llm.BatchLLM = claude.ClaudeBatch("k", client=batch_client(FakeBatches()))
    assert b.model == "claude-opus-5-5"


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
