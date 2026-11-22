"""주 계산 (SPEC 결정 18 · 72).

- **2026-11-08 주까지(옛 정의, 결정 18)**: 일요일 ~ 토요일, 이름은 시작일(일요일)의 ISO 날짜.
- **2026-11-14 주부터(결정 72)**: 토요일 ~ 금요일 7일, 이름은 시작일(토요일)의 ISO 날짜.
  전환점에서 11-14 하루가 마지막 옛 주(11-08 ~ 11-14)와 첫 새 주(11-14 ~ 11-20)에 겹친다.
  옛 주의 파일·이름은 그대로 둔다(한 번 쓴 주간 파일은 다시 쓰지 않는다).

하루 경계는 히스토리 API 그대로 UTC 0시(KST 09시)다. 「지난 주 · N주 전」은 날짜 산술(7일)로 세지 않고
이 모듈의 함수로만 센다 — 전환점에서는 앞 주와 6일 차이다.

히스토리 API 의 주(**API 주**)는 계속 일요일 시작이다 — `api_week_start` · `api_day_index` ·
`from_api_timestamp` 가 다룬다. API 주 → 우리 주 변환은 `core.history` 가 한다.
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

CUTOVER = date(2026, 11, 14)   # 첫 새 주(토요일). 이 날부터 주는 토 ~ 금
LAST_OLD = date(2026, 11, 8)   # 마지막 옛 주(일요일) — 11-14 까지
_SATURDAY = 5  # date.weekday(): 월=0 … 일=6
_SUNDAY = 6
# 시간대는 UTC-12 ~ UTC+14 이므로 실제 경계는 일요일 0시(UTC)에서 최대 14시간 떨어진다.
# 그보다 훨씬 먼 값은 형식이 예상과 다르다는 뜻이라 받아들이지 않는다.
_MAX_BOUNDARY_DRIFT = timedelta(hours=36)


def week_start(d: date) -> date:
    """d 가 속한 주의 시작일. 전환점 앞 날짜는 일요일, 전환점부터는 토요일.

    11-14 는 두 주에 겹치지만 새 주(11-14)를 돌려준다 — 옛 주에도 드는지는 `contains` 로 본다.
    """
    if d >= CUTOVER:
        return d - timedelta(days=(d.weekday() - _SATURDAY) % 7)
    return api_week_start(d)


def week_end(start: date) -> date:
    """주의 마지막 날 — 옛 주는 토요일, 새 주는 금요일."""
    _require_start(start)
    return start + timedelta(days=6)


def week_name(start: date) -> str:
    _require_start(start)
    return start.isoformat()


def parse_week(name: str) -> date:
    d = date.fromisoformat(name)
    _require_start(d)
    return d


def is_week_start(d: date) -> bool:
    return week_start(d) == d


def day_index(d: date) -> int:
    """d 가 그 주(`week_start(d)`)의 몇 번째 날인가. 주 시작일 0 … 마지막 날 6."""
    return (d - week_start(d)).days


def days_of(start: date) -> tuple[date, ...]:
    """주의 7일, 시작일부터."""
    _require_start(start)
    return tuple(start + timedelta(days=i) for i in range(7))


def previous_week(start: date) -> date:
    """바로 앞 주. 첫 새 주(11-14)의 앞 주는 마지막 옛 주(11-08)다."""
    _require_start(start)
    return week_start(start - timedelta(days=1))


def weeks_back(start: date, k: int) -> date:
    """k 주 전의 주 (k=0 이면 그 주)."""
    if k < 0:
        raise ValueError(f"k 는 0 이상이어야 한다: {k}")
    _require_start(start)
    w = start
    for _ in range(k):
        w = previous_week(w)
    return w


def iter_weeks_back(start: date, count: int) -> Iterator[date]:
    """start 부터 과거로 count 주. 히스토리 API 처럼 최신 주가 먼저다."""
    _require_start(start)
    w = start
    for i in range(count):
        if i:
            w = previous_week(w)
        yield w


def weeks_between(a: date, b: date) -> int:
    """a 주에서 b 주까지 몇 주인가(b 가 뒤면 양수). 전환점을 지나도 주 단위로 센다."""
    return _ordinal(b) - _ordinal(a)


def contains(start: date, d: date) -> bool:
    """d 가 start 주(7일)에 드는가. 11-14 는 11-08 주와 11-14 주 모두에 든다."""
    _require_start(start)
    return start <= d <= start + timedelta(days=6)


def api_week_start(d: date) -> date:
    """d 가 든 API 주의 시작일(일요일) — 히스토리 API 의 주는 전환점과 상관없이 일요일 시작이다."""
    return d - timedelta(days=(d.weekday() + 1) % 7)


def api_day_index(d: date) -> int:
    """히스토리 API days 배열의 위치. 일요일 0 … 토요일 6."""
    return (d.weekday() + 1) % 7


def from_api_timestamp(ts: int) -> date:
    """히스토리 API 의 `week` 타임스탬프 → API 주 시작일(일요일)."""
    return _nearest_sunday_midnight(ts).date()


def utc_offset_hours(ts: int) -> float:
    """주 경계가 어느 시간대의 일요일 0시인지 (예: KST 면 9.0). probe 가 기록한다."""
    instant = datetime.fromtimestamp(ts, tz=UTC)
    return (_nearest_sunday_midnight(ts) - instant).total_seconds() / 3600


def _ordinal(start: date) -> int:
    """주 순번 — 마지막 옛 주가 0, 첫 새 주가 1."""
    _require_start(start)
    if start >= CUTOVER:
        return (start - CUTOVER).days // 7 + 1
    return (start - LAST_OLD).days // 7


def _nearest_sunday_midnight(ts: int) -> datetime:
    instant = datetime.fromtimestamp(ts, tz=UTC)
    midnight = instant.replace(hour=0, minute=0, second=0, microsecond=0)
    before = midnight - timedelta(days=(midnight.weekday() - _SUNDAY) % 7)
    after = before + timedelta(days=7)
    nearest = before if instant - before <= after - instant else after
    if abs(instant - nearest) > _MAX_BOUNDARY_DRIFT:
        raise ValueError(f"주 경계 타임스탬프로 보기 어렵다: {ts} ({instant.isoformat()})")
    return nearest


def _require_start(d: date) -> None:
    if not is_week_start(d):
        kind = "토요일" if d >= CUTOVER else "일요일"
        raise ValueError(f"주 시작일은 {kind}이어야 한다(결정 72 — {CUTOVER.isoformat()} 부터 토요일): "
                         f"{d.isoformat()}")
