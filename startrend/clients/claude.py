"""실제 Claude 클라이언트 (SPEC FR-3.10, 결정 26) — Anthropic SDK 를 쓰는 유일한 파일(하네스가 강제한다).

- 정해진 형식 출력: output_config.format = json_schema.
  도구 강제 호출(tool_choice)은 Opus 5.5 에서 400 이라 쓰지 않는다.
- 사고는 끌 수 없다 — thinking 을 보내지 않는다(adaptive 와 같다). 깊이는 output_config.effort 로.
- 거절(refusal): 서버 쪽 대체 모델 `fallbacks="default"`(베타 server-side-fallback-2026-07-01)로
  같은 호출 안에서 다시 받는다. Batch API 는 fallbacks 를 받지 않으므로
  그쪽은 fallbacks=False 로 만든다(FR-3.10 ③).
- 키는 STARTREND_ANTHROPIC_API_KEY 에서 받아 넘긴다(NFR-8). 비용은 예산 계량기가 요청한 모델 단가로 센다.
"""

from typing import Any

from startrend.clients.llm import LLMRequest, LLMResponse, Usage

MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


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
        if self._fallbacks:
            msg = self._client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **params)
        else:
            msg = self._client.messages.create(**params)
        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
        u = msg.usage
        usage = Usage(u.input_tokens or 0, u.output_tokens or 0,
                      getattr(u, "cache_read_input_tokens", 0) or 0,
                      getattr(u, "cache_creation_input_tokens", 0) or 0)
        stop = str(msg.stop_reason or "")
        return LLMResponse(text=text, stop_reason=stop, usage=usage, model=str(msg.model))
