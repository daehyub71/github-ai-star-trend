"""예산 계량기 (SPEC NFR-3, FR-11.2, 결정 31 · PLAN 1-5). LLMClient 를 감싼다.

모든 LLM 호출은 이것을 지난다. 부르기 **전에** 최악의 비용(입력 추정 + max_tokens 전부 출력)을 잡아
상한을 넘을 수 있으면 부르지 않고 BudgetExceeded 를 올린다 — 그래서 실제 지출은 상한을 넘지 않는다.
단계는 이 예외를 받으면 LLM 단계만 멈추고, 비용 0 인 결과는 그대로 내보낸다(FR-11.2).

Batch(FR-3.7)는 run_batch 로만 보낸다 — 제출 전에 묶음 전체의 최악 비용(Batch 단가)으로 막고,
Batch ID 를 상태 파일에 남겨 끊겨도 같은 묶음을 다시 사지 않는다(원칙 5).
"""

import re
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from startrend.clients.llm import (
    BatchItem,
    BatchLLM,
    LLMClient,
    LLMRequest,
    LLMResponse,
    Usage,
    cost,
    estimate_tokens,
)
from startrend.core import hashing, io

_CUSTOM_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")  # Batch API 의 custom_id 규칙


class BudgetExceeded(RuntimeError):
    """이 호출을 하면 예산 상한을 넘을 수 있다."""


class BatchTimeout(RuntimeError):
    """Batch 가 정한 시간 안에 끝나지 않았다 — 상태 파일이 남아 다음 실행이 이어 받는다."""


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

    def worst_case(self, req: LLMRequest, *, batch: bool | None = None, model: str | None = None) -> float:
        est = Usage(input_tokens=estimate_tokens(req.system + req.user), output_tokens=req.max_tokens)
        return cost(model or self.model, est, batch=self.batch if batch is None else batch)

    def reserve(self, reqs: Iterable[LLMRequest], *, batch: bool, model: str | None = None) -> float:
        """부르기 전 확인. 최악의 비용 합이 남은 예산을 넘으면 BudgetExceeded. 최악 합을 돌려준다."""
        reqs = list(reqs)
        worst = sum(self.worst_case(r, batch=batch, model=model) for r in reqs)
        if self.spent + worst > self.cap_usd:
            what = (reqs[0].purpose if reqs else "") or "LLM"
            n = f" {len(reqs)}건" if len(reqs) > 1 else ""
            raise BudgetExceeded(f"{what}{n}: 최악 ${worst:.4f} — 남은 예산 ${self.remaining:.4f}")
        return worst

    def record(self, purpose: str, resp: LLMResponse, *, batch: bool, model: str | None = None) -> float:
        actual = cost(model or self.model, resp.usage, batch=batch)
        self.spent += actual
        self.calls += 1
        u = resp.usage
        self.ledger.append({"purpose": purpose, "model": resp.model, "stop_reason": resp.stop_reason,
                            "input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                            "cost_usd": round(actual, 6), "batch": batch})
        return actual

    def complete(self, req: LLMRequest) -> LLMResponse:
        self.reserve([req], batch=self.batch)
        resp = self.inner.complete(req)
        self.record(req.purpose, resp, batch=self.batch)
        return resp


def _fingerprint(model: str, reqs: Mapping[str, LLMRequest]) -> str:
    return hashing.content_hash({"model": model, "requests": {
        cid: {"system": r.system, "user": r.user, "max_tokens": r.max_tokens, "effort": r.effort,
              "schema": r.schema} for cid, r in reqs.items()}})


def run_batch(meter: BudgetMeter, client: BatchLLM, reqs: Mapping[str, LLMRequest], *, state: Path,
              sleep: Callable[[float], None] = time.sleep, poll_seconds: float = 60.0,
              max_wait_seconds: float = 26 * 3600,
              log: Callable[[str], None] = print) -> dict[str, BatchItem]:
    """묶음을 보내고 끝날 때까지 기다려 결과를 돌려준다. 실패한 건은 BatchItem.error 로 돌아온다.

    state: 이 묶음의 상태 파일. 같은 요청으로 다시 부르면 새로 제출하지 않고 그 묶음을 이어 받는다.
    이미 결과를 받은 묶음이면 결과만 다시 받고 장부에는 다시 적지 않는다(같은 돈을 두 번 세지 않는다).
    """
    if not reqs:
        return {}
    bad = [c for c in reqs if not _CUSTOM_ID.match(c)]
    if bad:
        raise ValueError(f"custom_id 는 영문·숫자·_·- 1~64자: {bad[:3]}")
    fp = _fingerprint(client.model, reqs)
    st: dict[str, Any] = io.read_json(state) if state.exists() else {}
    if st.get("fingerprint") == fp:
        bid = str(st["batch_id"])
        log(f"  묶음 이어 받기: {bid} ({st.get('status')})")
    else:
        if st:
            log(f"  이전 묶음 {st.get('batch_id')} 와 요청이 달라 새로 제출한다")
        worst = meter.reserve(reqs.values(), batch=True, model=client.model)
        bid = client.submit(reqs)
        st = {"batch_id": bid, "fingerprint": fp, "count": len(reqs), "status": "submitted",
              "submitted_at": datetime.now(UTC).isoformat(timespec="seconds"), "worst_usd": round(worst, 4)}
        io.write_json(state, st)
        log(f"  묶음 제출: {bid} · {len(reqs)}건 · 최악 ${worst:.2f}")
    waited = 0.0
    while not client.ended(bid):
        if waited >= max_wait_seconds:
            raise BatchTimeout(f"{bid}: {waited / 3600:.1f}시간 기다려도 끝나지 않았다 "
                               "— 다시 실행하면 이어 받는다")
        sleep(poll_seconds)
        waited += poll_seconds
    out = client.results(bid)
    if st.get("status") != "collected":
        for cid, item in out.items():
            if item.response is not None:
                meter.record(reqs[cid].purpose if cid in reqs else "", item.response, batch=True,
                             model=client.model)
        st["status"] = "collected"
        io.write_json(state, st)
    return out
