"""LLM 인터페이스 (SPEC FR-3.10, PLAN 1-2·1-5). 기본 구현은 mock — 실제 Claude 는 clients/claude.py.

단계 코드는 이 모양만 안다. 모든 실제 호출은 예산 계량기(startrend/budget.py)로 감싸서 넘긴다.
"""

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

# 100만 토큰당 달러 (2026-09-25 공식 표 — MEASURE §9). Batch 는 절반.
PRICES: dict[str, dict[str, float]] = {
    "claude-opus-5-5": {"input": 4.0, "output": 20.0, "cache_read": 0.20, "cache_write": 5.0},
}


@dataclass(frozen=True)
class LLMRequest:
    system: str                      # 지시문 — 호출마다 같아서 캐시 대상
    user: str                        # 입력 — 외부 콘텐츠는 데이터로만 넣는다(NFR-7)
    max_tokens: int
    effort: str = "low"              # FR-3.10 ① — 분류는 low 부터
    schema: dict[str, Any] | None = None   # 정해진 형식 출력(output_config.format) — FR-3.10 ②
    purpose: str = ""                # 계량기 장부용


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cache_read: int = 0
    cache_write: int = 0


@dataclass(frozen=True)
class LLMResponse:
    text: str
    stop_reason: str                 # "end_turn" · "max_tokens" · "refusal" … — FR-3.10 ③ 먼저 확인한다
    usage: Usage
    model: str


class LLMClient(Protocol):
    @property
    def model(self) -> str: ...

    def complete(self, req: LLMRequest) -> LLMResponse: ...


@dataclass(frozen=True)
class BatchItem:
    """Batch 결과 한 건. response 가 없으면 error 에 이유(errored:… · canceled · expired)."""
    response: LLMResponse | None
    error: str | None = None


class BatchLLM(Protocol):
    """Message Batches (FR-3.7) — 요청을 묶어 보내고(50% 할인), 끝나면 결과를 받는다.

    직접 부르지 않는다 — budget.run_batch 가 예산·상태 파일과 함께 부른다.
    """
    @property
    def model(self) -> str: ...

    def submit(self, reqs: Mapping[str, LLMRequest]) -> str: ...

    def ended(self, batch_id: str) -> bool: ...

    def results(self, batch_id: str) -> dict[str, BatchItem]: ...


def cost(model: str, usage: Usage, *, batch: bool = False) -> float:
    p = PRICES[model]
    usd = (usage.input_tokens * p["input"] + usage.output_tokens * p["output"]
           + usage.cache_read * p["cache_read"] + usage.cache_write * p["cache_write"]) / 1_000_000
    return usd / 2 if batch else usd


def estimate_tokens(text: str) -> int:
    """보수적 추정 — UTF-8 바이트 ÷ 3.

    영어는 실제보다 약 1.3배(토크나이저 차이 1.35배를 덮는다), 한국어는 1자 ≈ 1토큰.
    """
    return math.ceil(len(text.encode("utf-8")) / 3)


@dataclass
class MockLLM:
    """준비한 응답(목록) 또는 함수로 답한다. 받은 요청을 남긴다."""
    script: list[LLMResponse] | Callable[[LLMRequest], LLMResponse]
    model: str = "claude-opus-5-5"
    requests: list[LLMRequest] = field(default_factory=list)

    def complete(self, req: LLMRequest) -> LLMResponse:
        self.requests.append(req)
        if callable(self.script):
            return self.script(req)
        assert self.script, "MockLLM: 준비한 응답보다 많이 불렀다"
        return self.script.pop(0)


@dataclass
class MockBatchLLM:
    """함수로 답하는 가짜 Batch. 함수가 문자열을 돌려주면 그 이유로 실패한 건이다.

    묶음마다 polls_until_end 번째 확인에서 끝난다. 제출한 묶음을 남긴다.
    """
    answer: Callable[[LLMRequest], LLMResponse | str]
    model: str = "claude-opus-5-5"
    polls_until_end: int = 1
    submitted: dict[str, dict[str, LLMRequest]] = field(default_factory=dict)
    polls: dict[str, int] = field(default_factory=dict)

    def submit(self, reqs: Mapping[str, LLMRequest]) -> str:
        bid = f"msgbatch_mock_{len(self.submitted) + 1}"
        self.submitted[bid] = dict(reqs)
        return bid

    def ended(self, batch_id: str) -> bool:
        self.polls[batch_id] = self.polls.get(batch_id, 0) + 1
        return self.polls[batch_id] >= self.polls_until_end

    def results(self, batch_id: str) -> dict[str, BatchItem]:
        out: dict[str, BatchItem] = {}
        for cid, r in self.submitted[batch_id].items():
            a = self.answer(r)
            out[cid] = BatchItem(a) if isinstance(a, LLMResponse) else BatchItem(None, a)
        return out
