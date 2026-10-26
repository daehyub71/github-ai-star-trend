"""core.week — 주는 일요일~토요일, 이름은 시작일(일요일) (SPEC 결정 18)."""

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
    # 히스토리 API 의 days 배열은 일요일부터 시작한다
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
