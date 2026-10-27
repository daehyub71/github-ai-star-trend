"""Batch 경로 — clients.llm 의 Batch 인터페이스·mock 과 budget.run_batch (FR-3.7, NFR-3, 원칙 5).

돈이 나가는 묶음이라 세 가지를 지킨다:
- 제출 **전에** 묶음 전체의 최악 비용으로 막는다
- Batch ID 를 상태 파일에 남겨 끊겨도 같은 묶음을 다시 사지 않는다
- 끝나면 실제 사용량(Batch 단가)으로 장부에 적는다
"""

from typing import Any

import pytest

from startrend import budget
from startrend.clients import llm

OPUS = "claude-opus-5-5"


def req(user: str = "u" * 300, max_tokens: int = 1000) -> llm.LLMRequest:
    return llm.LLMRequest(system="s" * 300, user=user, max_tokens=max_tokens, purpose="classify")


def resp(inp: int = 1000, out: int = 100, text: str = "{}", stop: str = "end_turn") -> llm.LLMResponse:
    return llm.LLMResponse(text=text, stop_reason=stop, usage=llm.Usage(inp, out), model=OPUS)


def quiet(tmp_path) -> dict[str, Any]:
    """상태 파일 · 기다리지 않는 sleep · 조용한 로그."""
    return {"state": tmp_path / "b.json", "sleep": Sleeps(), "log": lambda s: None}


def meter(cap: float = 10.0) -> budget.BudgetMeter:
    return budget.BudgetMeter(llm.MockLLM([], model=OPUS), cap_usd=cap)


class Sleeps:
    def __init__(self, stop_after: int | None = None):
        self.calls: list[float] = []
        self.stop_after = stop_after

    def __call__(self, s: float) -> None:
        self.calls.append(s)
        if self.stop_after is not None and len(self.calls) >= self.stop_after:
            raise KeyboardInterrupt  # 기다리다 끊긴 실행


# --- mock ---


def test_batch_mock_answers_each_request_and_reports_errors():
    m = llm.MockBatchLLM(lambda r: "errored:overloaded" if r.user == "bad" else resp(text=r.user[:2]),
                         polls_until_end=2)
    bid = m.submit({"a": req(user="ok"), "b": req(user="bad")})
    assert not m.ended(bid) and m.ended(bid)
    out = m.results(bid)
    assert out["a"].response is not None and out["a"].response.text == "ok"
    assert out["b"].response is None and out["b"].error == "errored:overloaded"


def test_batch_mock_is_a_batch_client():
    m: llm.BatchLLM = llm.MockBatchLLM(lambda r: resp())
    assert m.model == OPUS


# --- run_batch ---


def test_budget_run_batch_returns_results_and_records_half_price(tmp_path):
    m, sleeps = llm.MockBatchLLM(lambda r: resp(1000, 100), polls_until_end=3), Sleeps()
    mt = meter()
    out = budget.run_batch(mt, m, {"r1-1": req(), "r2-1": req()}, state=tmp_path / "b.json", sleep=sleeps,
                           poll_seconds=30, log=lambda s: None)
    assert set(out) == {"r1-1", "r2-1"}
    assert mt.spent == pytest.approx(2 * (1000 * 4e-6 + 100 * 20e-6) / 2)   # Batch 는 절반
    assert mt.calls == 2 and {e["batch"] for e in mt.ledger} == {True}
    assert sleeps.calls == [30, 30]                                         # 세 번째 확인에서 끝


def test_budget_run_batch_blocks_before_submit_when_worst_case_exceeds_cap(tmp_path):
    m = llm.MockBatchLLM(lambda r: resp())
    # 최악(Batch): 입력 추정 200 + 출력 1,000 → 건당 약 $0.0104, 3건 약 $0.031 > $0.02
    with pytest.raises(budget.BudgetExceeded):
        budget.run_batch(meter(cap=0.02), m, {f"r{i}-1": req() for i in range(3)}, state=tmp_path / "b.json",
                         sleep=Sleeps(), log=lambda s: None)
    assert m.submitted == {} and not (tmp_path / "b.json").exists()


def test_budget_run_batch_resumes_a_submitted_batch_instead_of_buying_it_again(tmp_path):
    m = llm.MockBatchLLM(lambda r: resp(), polls_until_end=3)
    reqs = {"r1-1": req(), "r2-1": req()}
    with pytest.raises(KeyboardInterrupt):        # 제출 뒤 기다리다 끊겼다
        budget.run_batch(meter(), m, reqs, state=tmp_path / "b.json", sleep=Sleeps(stop_after=1),
                         log=lambda s: None)
    assert len(m.submitted) == 1 and (tmp_path / "b.json").exists()
    mt = meter()
    out = budget.run_batch(mt, m, reqs, **quiet(tmp_path))
    assert len(m.submitted) == 1 and set(out) == set(reqs)   # 다시 제출하지 않았다
    assert mt.calls == 2                                      # 이번 실행 장부에 처음 적힌다


def test_budget_run_batch_collected_state_refetches_without_counting_again(tmp_path):
    m = llm.MockBatchLLM(lambda r: resp())
    reqs = {"r1-1": req()}
    budget.run_batch(meter(), m, reqs, **quiet(tmp_path))
    mt = meter()
    out = budget.run_batch(mt, m, reqs, **quiet(tmp_path))
    assert len(m.submitted) == 1 and set(out) == {"r1-1"}
    assert mt.spent == 0 and mt.calls == 0                    # 이미 장부에 적은 돈 — 두 번 세지 않는다


def test_budget_run_batch_new_requests_get_a_new_batch(tmp_path):
    m = llm.MockBatchLLM(lambda r: resp())
    budget.run_batch(meter(), m, {"r1-1": req()}, **quiet(tmp_path))
    budget.run_batch(meter(), m, {"r2-1": req()}, **quiet(tmp_path))
    assert len(m.submitted) == 2


def test_budget_run_batch_gives_up_waiting_but_keeps_state(tmp_path):
    m = llm.MockBatchLLM(lambda r: resp(), polls_until_end=10**6)
    with pytest.raises(budget.BatchTimeout):
        budget.run_batch(meter(), m, {"r1-1": req()}, state=tmp_path / "b.json", sleep=Sleeps(),
                         poll_seconds=60, max_wait_seconds=180, log=lambda s: None)
    assert (tmp_path / "b.json").exists()                     # 다음 실행이 이어 받는다


def test_budget_run_batch_errored_items_cost_nothing(tmp_path):
    m = llm.MockBatchLLM(lambda r: "expired")
    mt = meter()
    out = budget.run_batch(mt, m, {"r1-1": req()}, **quiet(tmp_path))
    assert out["r1-1"].error == "expired" and mt.spent == 0


def test_budget_run_batch_rejects_invalid_custom_id(tmp_path):
    # API 규칙: custom_id 는 영문·숫자·_·- 1~64자
    with pytest.raises(ValueError):
        budget.run_batch(meter(), llm.MockBatchLLM(lambda r: resp()), {"owner/repo": req()},
                         **quiet(tmp_path))


def test_budget_run_batch_empty_does_nothing(tmp_path):
    m = llm.MockBatchLLM(lambda r: resp())
    assert budget.run_batch(meter(), m, {}, **quiet(tmp_path)) == {}
    assert m.submitted == {}
