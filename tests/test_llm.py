"""clients.llm + budget — LLM 인터페이스·mock·비용 계산과 예산 계량기 (NFR-3, FR-11.2, PLAN 1-5)."""

import json
from pathlib import Path

import pytest

from startrend import budget
from startrend.clients import llm

OPUS = "claude-opus-5-5"


def req(user: str = "x" * 300, max_tokens: int = 1000, system: str = "s" * 300) -> llm.LLMRequest:
    return llm.LLMRequest(system=system, user=user, max_tokens=max_tokens, purpose="test")


def resp(inp: int = 100, out: int = 50, text: str = "{}", stop: str = "end_turn") -> llm.LLMResponse:
    return llm.LLMResponse(text=text, stop_reason=stop, usage=llm.Usage(inp, out), model=OPUS)


# --- 비용 ---


def test_llm_cost_uses_model_price_table():
    # Opus 5.5: 입력 $4 · 출력 $20 · 캐시 읽기 $0.20 · 캐시 쓰기 $5 (100만 토큰당, MEASURE §9)
    u = llm.Usage(input_tokens=1_000_000, output_tokens=100_000, cache_read=1_000_000, cache_write=0)
    assert llm.cost(OPUS, u) == pytest.approx(4.0 + 2.0 + 0.2)
    assert llm.cost(OPUS, u, batch=True) == pytest.approx((4.0 + 2.0 + 0.2) / 2)


def test_llm_cost_unknown_model_is_an_error():
    with pytest.raises(KeyError):
        llm.cost("claude-unknown", llm.Usage(1, 1))


CALIBRATION = json.loads(
    (Path(__file__).parent / "fixtures" / "token_calibration.json").read_text(encoding="utf-8"))


def test_llm_estimate_tokens_is_bytes_over_1_5():
    assert llm.estimate_tokens("a" * 3000) == 2000
    assert llm.estimate_tokens("가" * 300) == 600          # 한국어 1자 = 3바이트
    assert llm.estimate_tokens("") == 0


def test_llm_request_tokens_cover_every_measured_request():
    # 회귀(P2-15, MEASURE §18): 바이트 ÷ 3 은 실측 200건 모두를 작게 잡았다(실제 ÷ 추정 중앙값 1.51).
    # 예산 계량기의 최악 비용은 실제보다 작으면 안 된다 — 정해진 형식 몫까지 더해 200건 모두를 덮는다
    for nbytes, actual in CALIBRATION["requests"]:
        assert llm.request_tokens("a" * nbytes, "", schema=True) >= actual, (nbytes, actual)


def test_llm_typical_request_tokens_sit_near_the_measured_median():
    ratios = sorted(llm.request_tokens("a" * b, "", schema=True, typical=True) / a
                    for b, a in CALIBRATION["requests"])
    assert 0.9 <= ratios[len(ratios) // 2] <= 1.1                # dry-run 하한은 실제에 가깝게


def test_llm_schema_share_is_counted_only_with_a_schema():
    assert llm.request_tokens("s", "u", schema=True) - llm.request_tokens("s", "u", schema=False) \
        == llm.SCHEMA_TOKENS


# --- mock ---


def test_llm_mock_replays_scripted_responses_and_records_requests():
    m = llm.MockLLM([resp(text="a"), resp(text="b")], model=OPUS)
    assert m.complete(req()).text == "a" and m.complete(req()).text == "b"
    assert len(m.requests) == 2
    with pytest.raises(AssertionError):
        m.complete(req())  # 준비한 응답보다 많이 부르면 테스트가 실패해야 한다


def test_llm_mock_can_answer_with_a_function():
    m = llm.MockLLM(lambda r: resp(text=r.user[:3]), model=OPUS)
    assert m.complete(req(user="hello")).text == "hel"


# --- 예산 계량기 ---


def test_budget_records_actual_cost():
    meter = budget.BudgetMeter(llm.MockLLM([resp(1000, 100)], model=OPUS), cap_usd=1.0)
    meter.complete(req())
    assert meter.spent == pytest.approx(1000 * 4e-6 + 100 * 20e-6)
    assert meter.calls == 1 and meter.ledger[0]["purpose"] == "test"


def test_budget_worst_case_includes_the_schema_share():
    meter = budget.BudgetMeter(llm.MockLLM([], model=OPUS), cap_usd=1.0)
    plain = req(max_tokens=0)
    shaped = llm.LLMRequest(system=plain.system, user=plain.user, max_tokens=0, schema={"type": "object"})
    assert meter.worst_case(shaped) - meter.worst_case(plain) == pytest.approx(llm.SCHEMA_TOKENS * 4e-6)


def test_budget_blocks_before_a_call_that_could_exceed_the_cap():
    inner = llm.MockLLM([resp()], model=OPUS)
    meter = budget.BudgetMeter(inner, cap_usd=0.01)
    # 최악: 입력 추정 400 + 출력 1,000 → 약 $0.0216 > $0.01 — 부르기 전에 멈춘다
    with pytest.raises(budget.BudgetExceeded):
        meter.complete(req(max_tokens=1000))
    assert inner.requests == [] and meter.spent == 0


def test_budget_counts_previous_spend():
    inner = llm.MockLLM([resp(0, 400), resp(0, 400)], model=OPUS)   # 실제 $0.008 씩
    meter = budget.BudgetMeter(inner, cap_usd=0.02)
    meter.complete(req(max_tokens=400, user="", system=""))
    meter.complete(req(max_tokens=400, user="", system=""))
    with pytest.raises(budget.BudgetExceeded):
        meter.complete(req(max_tokens=400, user="", system=""))      # 남은 $0.004 < 최악 $0.008
    assert meter.calls == 2


def test_budget_batch_prices_are_half():
    meter = budget.BudgetMeter(llm.MockLLM([resp(1000, 100)], model=OPUS), cap_usd=1.0, batch=True)
    meter.complete(req())
    assert meter.spent == pytest.approx((1000 * 4e-6 + 100 * 20e-6) / 2)


def test_budget_meter_is_an_llm_client():
    meter: llm.LLMClient = budget.BudgetMeter(llm.MockLLM([], model=OPUS), cap_usd=1.0)
    assert meter.model == OPUS
