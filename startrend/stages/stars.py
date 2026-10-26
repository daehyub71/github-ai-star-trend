"""주간 스타 (SPEC FR-2, 결정 27·29).

1. 이번 주·지난 주 전체 스냅샷의 차이(순증가)로 후보를 고른다
   — 증가량 상위, 성장률 상위, 새 저장소 상위, 추적 저장소.
2. 후보만 히스토리 API 로 달력 주(UTC 일~토)의 정확한 값과 요일별 수를 받는다.
   후보군 전체를 부르면 주 13시간이라 불가(MEASURE §2).
3. git 주간 파일에는 증가 ≥ 10 인 행만 쓴다 — 후보는 정밀 값, 나머지는 스냅샷 차이.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from startrend.clients.github import GitHubClient, GitHubError
from startrend.clients.github_parse import GitHubFormatError
from startrend.core import history, week, weekfile
from startrend.core.models import HistoryWeek
from startrend.core.snapshot import SnapRow
from startrend.core.weekfile import WeekRow

ZERO_DAYS = (0,) * 7


@dataclass(frozen=True)
class Exact:
    gain: int
    days: tuple[int, ...]
    stars_end: int


def exact_week(weeks: list[HistoryWeek], target: date, current_total: int) -> Exact:
    """히스토리에서 target 주의 값. 주 끝 스타는 core.history.week_end_stars (FR-2.6)."""
    t = next((w for w in weeks if w.week == target), None)
    return Exact(
        gain=t.total if t else 0,
        days=t.days if t else ZERO_DAYS,
        stars_end=history.week_end_stars(weeks, target, current_total=current_total),
    )


def select_candidates(cur: dict[int, SnapRow], prev: dict[int, SnapRow] | None, *, top_gain: int = 300,
                      top_growth: int = 300, top_new: int = 300, min_start: int = 1000,
                      tracked: Iterable[str] = (), fallback_top: int = 3000) -> list[SnapRow]:
    picked: list[int] = []

    def take(ids: Iterable[int]) -> None:
        for rid in ids:
            if rid not in picked:
                picked.append(rid)

    if prev is not None:
        gains = {rid: s.stars - prev[rid].stars for rid, s in cur.items() if rid in prev}
        take(sorted(gains, key=lambda r: (-gains[r], r))[:top_gain])
        growth = {rid: g / prev[rid].stars for rid, g in gains.items() if prev[rid].stars >= min_start}
        take(sorted(growth, key=lambda r: (-growth[r], r))[:top_growth])
    else:
        # 지난 주 스냅샷이 없다(FR-11.7) — 현재 스타 상위로 대신 고른다
        take(sorted(cur, key=lambda r: (-cur[r].stars, r))[:fallback_top])
    new = [rid for rid, s in cur.items() if "new" in s.sources]
    take(sorted(new, key=lambda r: (-cur[r].stars, r))[:top_new])
    by_name = {s.full_name: rid for rid, s in cur.items()}
    take(by_name[n] for n in tracked if n in by_name)
    return [cur[rid] for rid in picked]


def build_rows(cur: dict[int, SnapRow], prev: dict[int, SnapRow] | None,
               exact: dict[int, Exact]) -> list[WeekRow]:
    rows = []
    for rid, s in cur.items():
        if rid in exact:
            e = exact[rid]
            rows.append(WeekRow(rid, s.full_name, s.created, e.stars_end, e.gain, True, e.days))
        elif prev is not None and rid in prev:
            rows.append(WeekRow(rid, s.full_name, s.created, s.stars, s.stars - prev[rid].stars, False, None))
    return rows


def run_stars(gh: GitHubClient, *, cur: dict[int, SnapRow], prev: dict[int, SnapRow] | None, week_start: date,
              today: date, data_dir: Path, tracked: Iterable[str] = (), top_gain: int = 300,
              top_growth: int = 300, top_new: int = 300,
              log: Callable[[str], None] = print) -> dict[str, Any]:
    path = weekfile.week_path(data_dir, week_start)
    if path.exists():
        log(f"이미 있음 — 다시 쓰지 않는다: {path}")
        return {"written": False, "reason": "exists", "path": str(path)}
    if week_start != week.week_start(today) - timedelta(days=7):
        log(f"주의: {week_start} 는 막 끝난 주가 아니다 — 정밀 값의 주 끝 스타가 어긋날 수 있다")
    cands = select_candidates(cur, prev, top_gain=top_gain, top_growth=top_growth, top_new=top_new,
                              tracked=tracked)
    log(f"후보 {len(cands)}개 — 히스토리로 정밀 값")
    exact: dict[int, Exact] = {}
    failed: list[str] = []
    for s in cands:
        try:
            exact[s.id] = exact_week(gh.star_history(s.full_name), week_start, s.stars)
        except (GitHubError, GitHubFormatError):
            failed.append(s.full_name)
    rows = build_rows(cur, prev, exact)
    weekfile.write(path, rows)
    kept = sum(1 for r in rows if r.gain >= weekfile.MIN_GAIN)
    return {"written": True, "path": str(path), "candidates": len(cands), "exact": len(exact),
            "failed": failed, "rows": len(rows), "rows_kept": kept, "prev_snapshot": prev is not None}
