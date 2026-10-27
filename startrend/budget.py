"""예산 계량기 (SPEC NFR-3, FR-11.2, 결정 31 · PLAN 1-5). LLMClient 를 감싼다.

모든 LLM 호출은 이것을 지난다. 부르기 **전에** 최악의 비용(입력 추정 + max_tokens 전부 출력)을 잡아
상한을 넘을 수 있으면 부르지 않고 BudgetExceeded 를 올린다 — 그래서 실제 지출은 상한을 넘지 않는다.
단계는 이 예외를 받으면 LLM 단계만 멈추고, 비용 0 인 결과는 그대로 내보낸다(FR-11.2).
"""

from dataclasses import dataclass, field
from typing import Any

from startrend.clients.llm import LLMClient, LLMRequest, LLMResponse, Usage, cost, estimate_tokens


class BudgetExceeded(RuntimeError):
    """이 호출을 하면 예산 상한을 넘을 수 있다."""


@dataclass
class BudgetMeter:
    inner: LLMClient
    cap_usd: float
    batch: bool = False
    spent: float = 0.0
    calls: int = 0
    ledger: list[dict[str, Any]] = field(default_factory=list)

    @property
    def model(self) -> str:
        return self.inner.model

    @property
    def remaining(self) -> float:
        return self.cap_usd - self.spent

    def worst_case(self, req: LLMRequest) -> float:
        est = Usage(input_tokens=estimate_tokens(req.system + req.user), output_tokens=req.max_tokens)
        return cost(self.model, est, batch=self.batch)

    def complete(self, req: LLMRequest) -> LLMResponse:
        worst = self.worst_case(req)
        if self.spent + worst > self.cap_usd:
            what = req.purpose or "LLM"
            raise BudgetExceeded(f"{what}: 최악 ${worst:.4f} — 남은 예산 ${self.remaining:.4f}")
        resp = self.inner.complete(req)
        actual = cost(self.model, resp.usage, batch=self.batch)
        self.spent += actual
        self.calls += 1
        u = resp.usage
        self.ledger.append({"purpose": req.purpose, "model": resp.model, "stop_reason": resp.stop_reason,
                            "input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                            "cost_usd": round(actual, 6)})
        return resp
