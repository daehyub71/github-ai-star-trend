"""스타 히스토리 → 우리 주의 값 (SPEC FR-2.6, 결정 72).

히스토리 API 는 **API 주**(일요일 시작)마다 total 과 하루 값 7개(days, 일요일부터)를 준다.
우리 주는 2026-11-08 주까지 API 주와 같고(일 ~ 토), 2026-11-14 주부터는 토 ~ 금이다 —
새 주 S 의 하루 값 = API 주(S−6)의 토요일 + API 주(S+1)의 일 ~ 금. 그래서 하루 값으로 나눠 다시 묶는다.
옛 주는 API 주 하나와 같으니 예전처럼 그 주의 total · days 를 그대로 쓴다.

주 끝 스타 추정은 두 가지이고 둘 다 실제보다 작게 잡힌다.
- 역산: 현재 스타 − 주 마지막 날 뒤에 늘어난 값. 스냅샷을 찍은 뒤 히스토리를 받기까지 늘어난 만큼 작다.
- 누적 합: 히스토리에서 주 마지막 날까지 더한 값. 히스토리가 생성 시점까지 닿지 않으면 작다.
그래서 큰 쪽을 쓴다. 누적 합에는 그 주의 증가가 들어 있으니 주 시작 스타가 음수가 되지 않는다.
"""

from collections.abc import Sequence
from datetime import date, timedelta

from startrend.core import week
from startrend.core.models import HistoryWeek


def week_days(weeks: Sequence[HistoryWeek], start: date) -> tuple[int, ...]:
    """우리 주 start 의 하루 값 7개(주 시작일부터). 응답에 없는 API 주의 날은 0."""
    by = {w.week: w for w in weeks}
    out = []
    for d in week.days_of(start):
        w = by.get(week.api_week_start(d))
        out.append(w.days[week.api_day_index(d)] if w else 0)
    return tuple(out)


def week_gain(weeks: Sequence[HistoryWeek], start: date) -> int:
    """우리 주의 증가. API 주와 같은 주(옛 정의)는 API 의 total, 새 주는 하루 값 7개의 합."""
    if week.api_week_start(start) == start:
        t = next((w for w in weeks if w.week == start), None)
        return t.total if t else 0
    return sum(week_days(weeks, start))


def stars_at_day_end(weeks: Sequence[HistoryWeek], day: date, *, current_total: int) -> int:
    """day(UTC 하루)가 끝난 때의 스타 — 역산과 누적 합 중 큰 값."""
    up_to = after = 0
    for w in weeks:
        if w.week + timedelta(days=6) <= day:
            up_to += w.total
        elif w.week > day:
            after += w.total
        else:  # day 가 든 API 주 — 하루 값으로 나눈다
            i = week.api_day_index(day)
            up_to += sum(w.days[:i + 1])
            after += sum(w.days[i + 1:])
    return max(current_total - after, up_to, 0)


def week_end_stars(weeks: Sequence[HistoryWeek], target: date, *, current_total: int) -> int:
    """우리 주 target 의 마지막 날(옛 주 토요일 · 새 주 금요일)이 끝난 때의 스타."""
    return stars_at_day_end(weeks, week.week_end(target), current_total=current_total)
