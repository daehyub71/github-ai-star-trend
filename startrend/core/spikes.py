"""급등일 탐지 (SPEC FR-6.3) — 카드 ③ "왜 지금 떴나"는 코드가 찾은 급등일에서 시작한다.

일별 스타 수(주간 파일의 정밀 값, 요일별)에서 그날 수가 앞 LOOKBACK 일 중앙값의 MULT 배 이상이고
MIN_STARS 이상인 날을 고른다. 이어진 날들은 한 사건으로 묶고 가장 많은 날을 대표로 둔다.
정밀 값이 없는 날은 0 이 아니라 **모르는 날**이다 — 0 으로 보면 그 다음 날이 모두 급등처럼 보인다.
생성일 전은 0 으로 안다(출시일을 급등으로 잡기 위함). 앞선 기록이 MIN_HISTORY 일보다 적으면 판단하지 않는다.
기준값은 첫 카드 시범(P3-13)에서 실제 곡선을 보고 조정한다.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median

from startrend.core.weekfile import WeekRow

MIN_STARS = 100     # 하루 이만큼은 늘어야 급등으로 본다
MULT = 3.0          # 평소(앞 LOOKBACK 일 중앙값)의 몇 배
LOOKBACK = 14
MIN_HISTORY = 3     # 앞선 기록(알고 있는 날)이 이만큼은 있어야 판단한다
TOP = 3


@dataclass(frozen=True)
class Spike:
    day: date           # 사건에서 가장 많이 늘어난 날
    stars: int
    baseline: float     # 그날 앞 LOOKBACK 일 중앙값
    start: date         # 이어진 급등 날들의 처음과 끝
    end: date
    total: int          # 사건 동안 늘어난 합

    @property
    def ratio(self) -> float:
        return self.stars / max(self.baseline, 1.0)


def daily_from_weeks(rows: Mapping[date, WeekRow]) -> dict[date, int]:
    """{주 시작일: 그 주 행} → {날짜: 그날 증가}. 정밀 값(요일별 수)이 있는 주만."""
    out: dict[date, int] = {}
    for start, r in rows.items():
        if r.exact and r.days:
            out.update((start + timedelta(days=i), n) for i, n in enumerate(r.days))
    return out


def find_spikes(daily: Mapping[date, int], *, created: date | None = None, min_stars: int = MIN_STARS,
                mult: float = MULT, lookback: int = LOOKBACK, top: int = TOP) -> list[Spike]:
    """급등 사건을 많이 늘어난 순으로 top 개 골라 날짜순으로 돌려준다."""
    hits: dict[date, float] = {}
    for d in sorted(daily):
        prev: list[int] = []
        for k in range(1, lookback + 1):
            x = d - timedelta(days=k)
            if x in daily:
                prev.append(daily[x])
            elif created is not None and x < created:
                prev.append(0)
        if len(prev) < MIN_HISTORY:
            continue
        base = float(median(prev))
        if daily[d] >= min_stars and daily[d] >= mult * max(base, 1.0):
            hits[d] = base

    events: list[list[date]] = []
    for d in sorted(hits):
        if events and d - events[-1][-1] == timedelta(days=1):
            events[-1].append(d)
        else:
            events.append([d])
    spikes = []
    for g in events:
        peak = max(g, key=lambda x: (daily[x], -x.toordinal()))
        spikes.append(Spike(peak, daily[peak], hits[peak], g[0], g[-1], sum(daily[x] for x in g)))
    biggest = sorted(spikes, key=lambda s: (-s.stars, s.day))[:top]
    return sorted(biggest, key=lambda s: s.day)


def focus_days(spikes: list[Spike]) -> tuple[date, ...]:
    """근거 수집의 우선 날짜(Target.focus) — 사건마다 대표일."""
    return tuple(s.day for s in spikes)
