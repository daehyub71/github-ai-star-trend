"""주 계산. 주는 일요일 ~ 토요일이고, 이름은 시작일(일요일)의 ISO 날짜다 (SPEC 결정 18).

히스토리 API 의 주와 같은 정의다. API 는 주 경계가 UTC 와 맞는다고 보장하지 않으므로
타임스탬프는 가장 가까운 일요일 0시(UTC)로 맞춘다 (`from_api_timestamp`).
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

_SUNDAY = 6  # date.weekday(): 월=0 … 일=6
# 시간대는 UTC-12 ~ UTC+14 이므로 실제 경계는 일요일 0시(UTC)에서 최대 14시간 떨어진다.
# 그보다 훨씬 먼 값은 형식이 예상과 다르다는 뜻이라 받아들이지 않는다.
_MAX_BOUNDARY_DRIFT = timedelta(hours=36)


def week_start(d: date) -> date:
    """d 가 속한 주의 시작일(일요일)."""
    return d - timedelta(days=(d.weekday() + 1) % 7)


def week_end(start: date) -> date:
    """주의 마지막 날(토요일)."""
    _require_sunday(start)
    return start + timedelta(days=6)


def week_name(start: date) -> str:
    _require_sunday(start)
    return start.isoformat()


def parse_week(name: str) -> date:
    d = date.fromisoformat(name)
    _require_sunday(d)
    return d


def day_index(d: date) -> int:
    """히스토리 API days 배열의 위치. 일요일 0 … 토요일 6."""
    return (d.weekday() + 1) % 7


def previous_week(start: date) -> date:
    _require_sunday(start)
    return start - timedelta(days=7)


def iter_weeks_back(start: date, count: int) -> Iterator[date]:
    """start 부터 과거로 count 주. 히스토리 API 처럼 최신 주가 먼저다."""
    _require_sunday(start)
    for i in range(count):
        yield start - timedelta(days=7 * i)


def contains(start: date, d: date) -> bool:
    return week_start(d) == start


def from_api_timestamp(ts: int) -> date:
    """히스토리 API 의 `week` 타임스탬프 → 주 시작일."""
    return _nearest_sunday_midnight(ts).date()


def utc_offset_hours(ts: int) -> float:
    """주 경계가 어느 시간대의 일요일 0시인지 (예: KST 면 9.0). probe 가 기록한다."""
    instant = datetime.fromtimestamp(ts, tz=UTC)
    return (_nearest_sunday_midnight(ts) - instant).total_seconds() / 3600


def _nearest_sunday_midnight(ts: int) -> datetime:
    instant = datetime.fromtimestamp(ts, tz=UTC)
    midnight = instant.replace(hour=0, minute=0, second=0, microsecond=0)
    before = midnight - timedelta(days=(midnight.weekday() - _SUNDAY) % 7)
    after = before + timedelta(days=7)
    nearest = before if instant - before <= after - instant else after
    if abs(instant - nearest) > _MAX_BOUNDARY_DRIFT:
        raise ValueError(f"주 경계 타임스탬프로 보기 어렵다: {ts} ({instant.isoformat()})")
    return nearest


def _require_sunday(d: date) -> None:
    if d.weekday() != _SUNDAY:
        raise ValueError(f"주 시작일은 일요일이어야 한다: {d.isoformat()}")
