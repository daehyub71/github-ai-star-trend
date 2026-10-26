"""core.history — 히스토리로 주 끝 스타 추정 (FR-2.6)."""

from datetime import date

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
