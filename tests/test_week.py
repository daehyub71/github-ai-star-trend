"""core.week — 주 정의 (SPEC 결정 18 · 72).

2026-11-08 주까지는 일요일~토요일(이름은 시작 일요일), 2026-11-14 주부터는 토요일~금요일(이름은 시작 토요일).
11-14 하루는 두 주에 겹친다. 히스토리 API 의 주(API 주)는 계속 일요일 시작이다.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from startrend.core import week


def _ts(dt: datetime) -> int:
    return int(dt.timestamp())


def test_week_start_of_sunday_is_itself():
    assert week.week_start(date(2026, 10, 25)) == date(2026, 10, 25)


def test_week_start_of_saturday_is_previous_sunday():
    assert week.week_start(date(2026, 10, 31)) == date(2026, 10, 25)


def test_week_start_of_monday():
    assert week.week_start(date(2026, 10, 26)) == date(2026, 10, 25)


def test_week_end_is_saturday():
    assert week.week_end(date(2026, 10, 25)) == date(2026, 10, 31)


def test_week_name_round_trip():
    name = week.week_name(date(2026, 10, 25))
    assert name == "2026-10-25"
    assert week.parse_week(name) == date(2026, 10, 25)


def test_week_name_rejects_non_sunday():
    with pytest.raises(ValueError):
        week.week_name(date(2026, 10, 26))


def test_parse_week_rejects_non_sunday():
    with pytest.raises(ValueError):
        week.parse_week("2026-10-26")


def test_day_index_sunday_zero_saturday_six():
    # 옛 정의의 주 — 주 시작(일요일) 0 … 토요일 6
    assert week.day_index(date(2026, 10, 25)) == 0
    assert week.day_index(date(2026, 10, 31)) == 6


def test_previous_week():
    assert week.previous_week(date(2026, 10, 25)) == date(2026, 10, 18)


def test_iter_weeks_backward_newest_first():
    weeks = list(week.iter_weeks_back(date(2026, 10, 25), 3))
    assert weeks == [date(2026, 10, 25), date(2026, 10, 18), date(2026, 10, 11)]


def test_from_api_timestamp_utc_midnight_sunday():
    ts = _ts(datetime(2026, 10, 25, 0, 0, tzinfo=UTC))
    assert week.from_api_timestamp(ts) == date(2026, 10, 25)


def test_from_api_timestamp_kst_midnight_sunday():
    # KST 일요일 0시 = UTC 토요일 15시 — UTC 날짜로 자르면 토요일이 되어 틀린다
    ts = _ts(datetime(2026, 10, 24, 15, 0, tzinfo=UTC))
    assert week.from_api_timestamp(ts) == date(2026, 10, 25)


def test_from_api_timestamp_pst_midnight_sunday():
    # PST 일요일 0시 = UTC 일요일 8시
    ts = _ts(datetime(2026, 10, 25, 8, 0, tzinfo=UTC))
    assert week.from_api_timestamp(ts) == date(2026, 10, 25)


def test_from_api_timestamp_rejects_midweek():
    # 일요일 경계에서 36시간보다 멀면 예상 밖 형식이다 — 조용히 반올림하지 않는다
    ts = _ts(datetime(2026, 10, 28, 12, 0, tzinfo=UTC))
    with pytest.raises(ValueError):
        week.from_api_timestamp(ts)


def test_utc_offset_hours_reports_boundary_alignment():
    # probe 가 API 의 주 경계가 어느 시간대 기준인지 기록할 때 쓴다
    kst = _ts(datetime(2026, 10, 24, 15, 0, tzinfo=UTC))
    assert week.utc_offset_hours(kst) == 9.0
    utc = _ts(datetime(2026, 10, 25, 0, 0, tzinfo=UTC))
    assert week.utc_offset_hours(utc) == 0.0
    pst = _ts(datetime(2026, 10, 25, 8, 0, tzinfo=UTC))
    assert week.utc_offset_hours(pst) == -8.0


def test_week_contains():
    start = date(2026, 10, 25)
    assert week.contains(start, start + timedelta(days=6))
    assert not week.contains(start, start + timedelta(days=7))


# --- 결정 72: 2026-11-14 주부터 토요일 ~ 금요일 ---


def test_week_cutover_is_the_first_saturday_week():
    assert week.CUTOVER == date(2026, 11, 14)
    assert week.CUTOVER.weekday() == 5  # 토요일


def test_week_start_after_cutover_is_saturday():
    assert week.week_start(date(2026, 11, 14)) == date(2026, 11, 14)   # 토 — 그 자체
    assert week.week_start(date(2026, 11, 20)) == date(2026, 11, 14)   # 금 — 같은 주 마지막 날
    assert week.week_start(date(2026, 11, 21)) == date(2026, 11, 21)
    assert week.week_start(date(2026, 11, 22)) == date(2026, 11, 21)   # 일


def test_week_start_before_cutover_keeps_sunday():
    assert week.week_start(date(2026, 11, 13)) == date(2026, 11, 8)
    assert week.week_start(date(2026, 11, 10)) == date(2026, 11, 8)
    assert week.week_start(date(2026, 11, 8)) == date(2026, 11, 8)


def test_week_end_is_six_days_after_start_in_both_definitions():
    assert week.week_end(date(2026, 11, 8)) == date(2026, 11, 14)    # 옛 주 — 토
    assert week.week_end(date(2026, 11, 14)) == date(2026, 11, 20)   # 새 주 — 금
    assert week.week_end(date(2026, 11, 21)) == date(2026, 11, 27)


def test_week_names_accept_sunday_before_and_saturday_after_cutover():
    assert week.parse_week("2026-11-08") == date(2026, 11, 8)
    assert week.parse_week("2026-11-14") == date(2026, 11, 14)
    assert week.week_name(date(2026, 11, 21)) == "2026-11-21"
    for bad in ("2026-11-07",   # 전환점 앞 토요일
                "2026-11-15",   # 전환점 뒤 일요일
                "2026-11-20"):
        with pytest.raises(ValueError):
            week.parse_week(bad)
    with pytest.raises(ValueError):
        week.week_name(date(2026, 11, 15))


def test_previous_week_across_the_cutover():
    assert week.previous_week(date(2026, 11, 14)) == date(2026, 11, 8)    # 6일 차이
    assert week.previous_week(date(2026, 11, 21)) == date(2026, 11, 14)
    assert week.previous_week(date(2026, 11, 8)) == date(2026, 11, 1)
    with pytest.raises(ValueError):
        week.previous_week(date(2026, 11, 15))


def test_weeks_back_counts_weeks_not_days():
    assert week.weeks_back(date(2026, 11, 21), 0) == date(2026, 11, 21)
    assert week.weeks_back(date(2026, 11, 21), 2) == date(2026, 11, 8)
    assert week.weeks_back(date(2026, 11, 28), 4) == date(2026, 11, 1)


def test_iter_weeks_back_across_the_cutover():
    got = list(week.iter_weeks_back(date(2026, 11, 28), 4))
    assert got == [date(2026, 11, 28), date(2026, 11, 21), date(2026, 11, 14), date(2026, 11, 8)]


def test_weeks_between_counts_weeks_across_the_cutover():
    assert week.weeks_between(date(2026, 10, 18), date(2026, 11, 8)) == 3
    assert week.weeks_between(date(2026, 10, 18), date(2026, 11, 14)) == 4
    assert week.weeks_between(date(2026, 11, 8), date(2026, 11, 28)) == 3
    assert week.weeks_between(date(2026, 11, 21), date(2026, 11, 21)) == 0


def test_day_index_counts_from_the_week_start():
    assert week.day_index(date(2026, 11, 14)) == 0   # 토 — 새 주 첫날
    assert week.day_index(date(2026, 11, 20)) == 6   # 금
    assert week.day_index(date(2026, 11, 22)) == 1   # 일


def test_api_week_stays_sunday_based():
    # 히스토리 API 의 주와 days 배열(일요일 0 … 토요일 6)은 그대로다
    assert week.api_week_start(date(2026, 11, 14)) == date(2026, 11, 8)
    assert week.api_week_start(date(2026, 11, 22)) == date(2026, 11, 22)
    assert week.api_day_index(date(2026, 11, 14)) == 6   # 토
    assert week.api_day_index(date(2026, 11, 20)) == 5   # 금


def test_week_contains_the_overlap_day_in_both_weeks():
    # 11-14 하루는 마지막 옛 주와 첫 새 주에 함께 든다(결정 72)
    assert week.contains(date(2026, 11, 8), date(2026, 11, 14))
    assert week.contains(date(2026, 11, 14), date(2026, 11, 14))
    assert week.contains(date(2026, 11, 14), date(2026, 11, 20))
    assert not week.contains(date(2026, 11, 14), date(2026, 11, 13))
    assert not week.contains(date(2026, 11, 14), date(2026, 11, 21))


def test_week_days_lists_the_seven_dates():
    assert week.days_of(date(2026, 11, 14)) == tuple(date(2026, 11, 14) + timedelta(days=i) for i in range(7))


def test_week_local_run_today_is_the_first_new_week():
    # 2026-11-22(일) 로컬 실행 — trend_weekly_local.sh 의 WEEK, PREV 계산과 같은 식
    w = week.previous_week(week.week_start(date(2026, 11, 22)))
    assert (w, week.previous_week(w)) == (date(2026, 11, 14), date(2026, 11, 8))


def test_week_sunday_morning_kst_and_saturday_utc_agree():
    # 일 07:00 KST(로컬 date.today() = 일요일) 와 같은 순간의 UTC(토 22:00) 가 같은 주를 고른다
    kst = week.previous_week(week.week_start(date(2026, 11, 29)))
    utc = week.previous_week(week.week_start(date(2026, 11, 28)))
    assert kst == utc == date(2026, 11, 21)
