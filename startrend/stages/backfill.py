"""52주 소급 (SPEC FR-2.4, 결정 22) — 1회성 로컬 작업, 비용 0.

후보군(현재 스냅샷) 저장소마다 히스토리를 받아 과거 주마다 정확한 증가량·요일별 수·주 끝 스타를 계산하고,
주마다 git 주간 파일(증가 ≥ 10 행)을 쓴다. 히스토리 한 쪽은 30주라 30주보다 오래된 저장소만 2쪽을 부른다.
6.6만 개면 약 13만 회 · 26시간 분량 — 응답 캐시로 이어 돌린다. 지금 살아 있는 저장소만 남는 편향이 있다.
"""

from collections.abc import Callable, Iterable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from startrend.clients.github import HISTORY_PER_PAGE_MAX, GitHubClient, GitHubError
from startrend.clients.github_parse import GitHubFormatError
from startrend.core import history, week, weekfile
from startrend.core.models import HistoryWeek
from startrend.core.snapshot import SnapRow
from startrend.core.weekfile import WeekRow

ZERO_DAYS = (0,) * 7


def target_weeks(today: date, weeks_back: int) -> list[date]:
    """막 끝난 주부터 과거로 weeks_back 개 (최신 먼저)."""
    last = week.week_start(today) - timedelta(days=7)
    return list(week.iter_weeks_back(last, weeks_back))


def week_rows_from_history(row: SnapRow, weeks: list[HistoryWeek], *, today: date, weeks_back: int
                           ) -> dict[date, WeekRow]:
    by = {w.week: w for w in weeks}
    out: dict[date, WeekRow] = {}
    for t in target_weeks(today, weeks_back):
        if week.week_end(t) < row.created:
            break  # 아직 없던 주
        w = by.get(t)
        gain = w.total if w else 0
        days = w.days if w else ZERO_DAYS
        end = history.week_end_stars(weeks, t, current_total=row.stars)
        out[t] = WeekRow(row.id, row.full_name, row.created, end, gain, True, days)
    return out


def fetch_history(gh: GitHubClient, row: SnapRow, weeks_back: int) -> tuple[list[HistoryWeek], int]:
    """필요한 만큼만 쪽을 부른다. (주들, 호출 수)"""
    weeks = gh.star_history(row.full_name)
    calls = 1
    page = 1
    while (len(weeks) == HISTORY_PER_PAGE_MAX * page and weeks_back + 1 > len(weeks)
           and row.created < weeks[-1].week):
        page += 1
        more = gh.star_history(row.full_name, page=page)
        calls += 1
        if not more:
            break
        weeks.extend(more)
    return weeks, calls


def run_backfill(gh: GitHubClient, *, rows: Iterable[SnapRow], today: date, weeks_back: int, data_dir: Path,
                 log: Callable[[str], None] = print, progress_every: int = 1000) -> dict[str, Any]:
    targets = target_weeks(today, weeks_back)
    per_week: dict[date, list[WeekRow]] = {t: [] for t in targets}
    calls = 0
    failed: list[str] = []
    ordered = sorted(rows, key=lambda r: r.id)
    for i, row in enumerate(ordered, 1):
        try:
            weeks, n = fetch_history(gh, row, weeks_back)
        except (GitHubError, GitHubFormatError):
            failed.append(row.full_name)
            continue
        calls += n
        for t, wr in week_rows_from_history(row, weeks, today=today, weeks_back=weeks_back).items():
            if wr.gain >= weekfile.MIN_GAIN:
                per_week[t].append(wr)
        if i % progress_every == 0:
            log(f"  {i}/{len(ordered)} · 히스토리 {calls}회")
    written, kept = [], []
    for t in targets:
        path = weekfile.week_path(data_dir, t)
        if path.exists():
            kept.append(t.isoformat())  # 한 번 쓴 주간 파일은 그대로 둔다
            continue
        weekfile.write(path, per_week[t])
        written.append(t.isoformat())
    return {
        "repos": len(ordered), "history_calls": calls, "failed": failed,
        "weeks_written": len(written), "weeks_kept": kept,
        "rows_per_week": {t.isoformat(): len(per_week[t]) for t in targets},
    }
