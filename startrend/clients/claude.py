"""실제 Claude 클라이언트 (SPEC FR-3.10, 결정 26) — Anthropic SDK 를 쓰는 유일한 파일(하네스가 강제한다).

- 정해진 형식 출력: output_config.format = json_schema.
  도구 강제 호출(tool_choice)은 Opus 5.5 에서 400 이라 쓰지 않는다.
- 사고는 끌 수 없다 — thinking 을 보내지 않는다(adaptive 와 같다). 깊이는 output_config.effort 로.
- 거절(refusal): 서버 쪽 대체 모델 `fallbacks="default"`(베타 server-side-fallback-2026-07-01)로
  같은 호출 안에서 다시 받는다. Batch API 는 fallbacks 를 받지 않으므로
  그쪽(ClaudeBatch)은 fallbacks 없이 보내고, 거절된 건은 일반 호출로 다시 보낸다(FR-3.10 ③).
- 키는 STARTREND_ANTHROPIC_API_KEY 에서 받아 넘긴다(NFR-8). 비용은 예산 계량기가 요청한 모델 단가로 센다.
"""

from collections.abc import Mapping
from typing import Any

from startrend.clients.llm import BatchItem, LLMRequest, LLMResponse, Usage

MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
STREAM_OVER = 16_000     # 출력 상한이 이보다 크면 스트리밍(블로그 초안) — 카드·브리핑은 일반 호출 그대로


class ClaudeLLM:
    def __init__(self, api_key: str, *, model: str = MODEL, client: Any = None, fallbacks: bool = True):
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
        self._client = client
        self._model = model
        self._fallbacks = fallbacks

    def __repr__(self) -> str:
        return f"ClaudeLLM(model={self._model!r}, fallbacks={self._fallbacks})"

    @property
    def model(self) -> str:
        return self._model

    def params(self, req: LLMRequest) -> dict[str, Any]:
        """요청 본문 — Batch 경로도 같은 모양을 쓴다."""
        output: dict[str, Any] = {"effort": req.effort}
        if req.schema is not None:
            output["format"] = {"type": "json_schema", "schema": req.schema}
        return {"model": self._model, "max_tokens": req.max_tokens, "system": req.system,
                "messages": [{"role": "user", "content": req.user}], "output_config": output}

    def complete(self, req: LLMRequest) -> LLMResponse:
        params = self.params(req)
        api = self._client.beta.messages if self._fallbacks else self._client.messages
        if self._fallbacks:
            params = {"betas": [FALLBACK_BETA], "fallbacks": "default", **params}
        if req.max_tokens > STREAM_OVER:
            # 출력이 길면 일반 호출이 10분을 넘을 수 있다 — SDK 권장대로 스트리밍, 마지막 메시지만 쓴다
            with api.stream(**params) as stream:
                return _response(stream.get_final_message())
        return _response(api.create(**params))


class ClaudeBatch:
    """Message Batches 경로 (FR-3.7, 50% 할인). budget.run_batch 만 부른다.

    요청 모양은 ClaudeLLM.params 와 같다. Batch 는 fallbacks 를 받지 않으므로
    거절(refusal)된 건은 부른 쪽이 일반 호출(fallbacks)로 다시 보낸다(FR-3.10 ③).
    """

    def __init__(self, api_key: str, *, model: str = MODEL, client: Any = None):
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
        self._client = client
        self._shape = ClaudeLLM(api_key, model=model, client=client, fallbacks=False)

    def __repr__(self) -> str:
        return f"ClaudeBatch(model={self.model!r})"

    @property
    def model(self) -> str:
        return self._shape.model

    def submit(self, reqs: Mapping[str, LLMRequest]) -> str:
        requests = [{"custom_id": cid, "params": self._shape.params(r)} for cid, r in reqs.items()]
        return str(self._client.messages.batches.create(requests=requests).id)

    def ended(self, batch_id: str) -> bool:
        return str(self._client.messages.batches.retrieve(batch_id).processing_status) == "ended"

    def results(self, batch_id: str) -> dict[str, BatchItem]:
        out: dict[str, BatchItem] = {}
        for row in self._client.messages.batches.results(batch_id):
            res = row.result
            kind = str(getattr(res, "type", ""))
            if kind == "succeeded":
                out[str(row.custom_id)] = BatchItem(_response(res.message))
            elif kind == "errored":
                # 모양: {"type": "error", "error": {"type": "overloaded_error", ...}}
                err = getattr(res, "error", None)
                inner = getattr(err, "error", None)
                detail = getattr(inner, "type", None) or getattr(err, "type", None) or "unknown"
                out[str(row.custom_id)] = BatchItem(None, f"errored:{detail}")
            else:
                out[str(row.custom_id)] = BatchItem(None, kind or "unknown")   # canceled · expired
        return out


def _response(msg: Any) -> LLMResponse:
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    u = msg.usage
    usage = Usage(u.input_tokens or 0, u.output_tokens or 0,
                  getattr(u, "cache_read_input_tokens", 0) or 0,
                  getattr(u, "cache_creation_input_tokens", 0) or 0)
    return LLMResponse(text=text, stop_reason=str(msg.stop_reason or ""), usage=usage, model=str(msg.model))
