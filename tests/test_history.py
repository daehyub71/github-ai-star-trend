"""core.history — 히스토리로 주 끝 스타 추정 (FR-2.6)."""

from datetime import date, timedelta

from startrend.clients import github_parse as gp
from startrend.core import history
from tests import synth

CUR = date(2026, 10, 25)


def test_history_week_end_stars_backward_for_old_repo():
    # 오래된 저장소 — 히스토리가 일부만 있으니 현재 스타에서 거꾸로 뺀 값이 크다
    weeks = gp.parse_history(synth.history(CUR, [30, 700, 500]))
    assert history.week_end_stars(weeks, date(2026, 10, 18), current_total=5000) == 4970
    assert history.week_end_stars(weeks, date(2026, 10, 11), current_total=5000) == 4270


def test_history_week_end_stars_forward_when_backward_is_too_low():
    weeks = gp.parse_history(synth.history(CUR, [3000, 22015, 300]))
    assert history.week_end_stars(weeks, date(2026, 10, 18), current_total=23000) == 22315


def test_history_week_end_stars_never_below_week_gain():
    weeks = gp.parse_history(synth.history(CUR, [0, 500]))
    assert history.week_end_stars(weeks, date(2026, 10, 18), current_total=10) == 500


def test_history_week_end_stars_empty_history_is_current_total():
    assert history.week_end_stars([], date(2026, 10, 18), current_total=42) == 42


# --- 결정 72: API 주(일요일 시작) → 우리 주(2026-11-14 부터 토요일 시작) ---


def _api(newest: date, days_list: list[list[int]]) -> list[dict[str, object]]:
    """days 를 그대로 주는 히스토리 API 형식 — days_list[0] 이 newest 주(최신 주 먼저)."""
    return [{"week": synth.sunday_ts(newest - timedelta(days=7 * i)), "total": sum(d), "days": d}
            for i, d in enumerate(days_list)]


# API 주 11-22(진행 중, 일요일만) · 11-15 · 11-08 · 11-01
API = _api(date(2026, 11, 22), [[5, 0, 0, 0, 0, 0, 0],
                                [1, 2, 3, 4, 5, 6, 70],
                                [10, 10, 10, 10, 10, 10, 40],
                                [100] * 7])


def test_history_new_week_days_are_saturday_then_sunday_to_friday():
    weeks = gp.parse_history(API)
    # 11-14 주 = API 11-08 주의 토요일(40) + API 11-15 주의 일 ~ 금
    assert history.week_days(weeks, date(2026, 11, 14)) == (40, 1, 2, 3, 4, 5, 6)
    assert history.week_gain(weeks, date(2026, 11, 14)) == 61
    # 11-21 주 = API 11-15 주의 토요일(70) + API 11-22 주의 일 ~ 금(일요일만 들어옴)
    assert history.week_days(weeks, date(2026, 11, 21)) == (70, 5, 0, 0, 0, 0, 0)
    assert history.week_gain(weeks, date(2026, 11, 21)) == 75


def test_history_old_week_is_the_api_week_unchanged():
    weeks = gp.parse_history(API)
    assert history.week_days(weeks, date(2026, 11, 8)) == (10, 10, 10, 10, 10, 10, 40)
    assert history.week_gain(weeks, date(2026, 11, 8)) == 100


def test_history_old_week_gain_is_the_api_total_even_if_days_disagree():
    # 옛 주는 예전처럼 API 주의 total 을 쓴다(days 합과 다르면 contract 가 경고만 한다)
    raw = _api(date(2026, 11, 8), [[1] * 7])
    raw[0]["total"] = 99
    assert history.week_gain(gp.parse_history(raw), date(2026, 11, 8)) == 99


def test_history_missing_api_week_days_are_zero():
    weeks = gp.parse_history(_api(date(2026, 11, 22), [[5, 0, 0, 0, 0, 0, 0]]))
    assert history.week_days(weeks, date(2026, 11, 14)) == (0,) * 7
    assert history.week_gain(weeks, date(2026, 11, 14)) == 0


def test_history_new_week_end_stars_is_after_friday():
    weeks = gp.parse_history(API)
    # 금요일(11-20) 뒤에 늘어난 것: API 11-15 주 토요일 70 + API 11-22 주 5
    assert history.week_end_stars(weeks, date(2026, 11, 14), current_total=5000) == 5000 - 70 - 5
    # 11-21 주는 금요일(11-27) 뒤가 0
    assert history.week_end_stars(weeks, date(2026, 11, 21), current_total=5000) == 5000


def test_history_new_week_end_stars_forward_counts_days_up_to_friday():
    weeks = gp.parse_history(API)
    # 누적 합: 11-01 주 700 + 11-08 주 100 + 11-15 주 일 ~ 금 21 = 821 (역산 150 보다 크다)
    assert history.week_end_stars(weeks, date(2026, 11, 14), current_total=225) == 821


def test_history_old_week_end_stars_unchanged_by_the_cutover():
    weeks = gp.parse_history(API)
    # 마지막 옛 주(11-08 ~ 11-14 토) 끝 — 뒤의 API 주 둘(91 + 5)을 뺀다
    assert history.week_end_stars(weeks, date(2026, 11, 8), current_total=5000) == 5000 - 91 - 5
