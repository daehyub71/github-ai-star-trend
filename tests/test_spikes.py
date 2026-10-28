"""core.spikes — 일별 스타 곡선의 급등일을 코드로 찾는다 (FR-6.3). 카드 ③ 타임라인과 근거 우선순위의 기준."""

from datetime import date, timedelta

from startrend.core import spikes as sp
from startrend.core.weekfile import WeekRow

D0 = date(2026, 9, 27)   # 일요일


def _flat(days: int, per_day: int = 10, start: date = D0) -> dict[date, int]:
    return {start + timedelta(days=i): per_day for i in range(days)}


def test_spikes_daily_from_weeks_uses_exact_rows_only():
    rows = {
        date(2026, 10, 4): WeekRow(1, "o/r", D0, 500, 70, True, (10, 10, 10, 10, 10, 10, 10)),
        date(2026, 10, 11): WeekRow(1, "o/r", D0, 600, 100, False, None),
    }
    daily = sp.daily_from_weeks(rows)
    assert sorted(daily) == [date(2026, 10, 4) + timedelta(days=i) for i in range(7)]


def test_spikes_finds_a_single_jump_over_a_flat_baseline():
    daily = _flat(21)
    jump = D0 + timedelta(days=17)
    daily[jump] = 500
    [s] = sp.find_spikes(daily)
    assert s.day == jump and s.stars == 500 and s.baseline == 10 and s.ratio == 50
    assert (s.start, s.end, s.total) == (jump, jump, 500)


def test_spikes_merges_consecutive_days_into_one_event_at_the_peak():
    daily = _flat(21)
    for k, v in ((15, 300), (16, 800), (17, 400)):
        daily[D0 + timedelta(days=k)] = v
    [s] = sp.find_spikes(daily)
    assert s.day == D0 + timedelta(days=16) and s.stars == 800
    assert (s.start, s.end, s.total) == (D0 + timedelta(days=15), D0 + timedelta(days=17), 1500)


def test_spikes_ignores_small_absolute_jumps():
    daily = _flat(21, per_day=1)
    daily[D0 + timedelta(days=18)] = sp.MIN_STARS - 1
    assert sp.find_spikes(daily) == []


def test_spikes_ignores_steady_high_growth():
    assert sp.find_spikes(_flat(28, per_day=900)) == []


def test_spikes_launch_day_of_a_new_repo_counts():
    # 생성일 전은 0 으로 안다 — 그래서 첫날도 판단할 수 있다
    daily = {D0: 2000, D0 + timedelta(days=1): 700, D0 + timedelta(days=2): 150}
    [s] = sp.find_spikes(daily, created=D0)
    assert s.day == D0 and s.baseline == 0 and s.end == D0 + timedelta(days=2)


def test_spikes_needs_some_history_when_creation_is_unknown():
    # 생성일을 모르면 앞선 기록이 MIN_HISTORY 일 이상 있어야 판단한다 — 기록 첫날을 출시일로 오인하지 않는다
    daily = {D0: 2000, D0 + timedelta(days=1): 700, D0 + timedelta(days=2): 150}
    assert sp.find_spikes(daily) == []


def test_spikes_missing_days_are_unknown_not_zero():
    # 정밀 값이 없는 주(요일별 수 없음)를 0 으로 보면 그 다음 날이 모두 급등처럼 보인다
    daily = _flat(7, per_day=300)
    daily.update(_flat(7, per_day=300, start=D0 + timedelta(days=14)))
    assert sp.find_spikes(daily) == []


def test_spikes_keeps_the_biggest_events_in_date_order():
    daily = _flat(60)
    for k, v in ((10, 400), (25, 1200), (40, 300), (55, 900)):
        daily[D0 + timedelta(days=k)] = v
    got = sp.find_spikes(daily, top=3)
    assert [s.stars for s in got] == [400, 1200, 900]
    assert [s.day for s in got] == sorted(s.day for s in got)


def test_spikes_focus_days_are_the_peaks():
    daily = _flat(30)
    daily[D0 + timedelta(days=20)] = 500
    assert sp.focus_days(sp.find_spikes(daily)) == (D0 + timedelta(days=20),)
