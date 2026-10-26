"""후보 발굴 (SPEC FR-1, 결정 27).

이번 주 후보 = ① 스타 ≥ pool_min 전체 ② new_days 이내 생성·스타 ≥ new_min 새 저장소
③ 지난 주까지 랭킹에 들었던 저장소.
Search 는 질의 하나에 1,000건까지만 주므로 스타 구간을 반씩 나눠 구간마다 1,000건 이하가 되게 한다.
결과의 스타 수가 이번 주 전체 스냅샷이다(FR-1.4) — 지난 주 스냅샷과의 차이가 증가량 후보의 기준이다.
"""

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from startrend.clients.github import SEARCH_RESULT_CAP, GitHubClient, GitHubError
from startrend.core.models import Repo
from startrend.core.snapshot import SnapRow


@dataclass(frozen=True)
class Slice:
    lo: int
    hi: int
    total: int
    dense: bool = False  # 스타 값 하나에 상한보다 많다 — 더 나눌 수 없어 일부만 받는다


@dataclass
class DiscoverResult:
    rows: list[SnapRow]
    stats: dict[str, Any]


def slice_query(s: Slice, extra: str = "") -> str:
    return f"stars:{s.lo}..{s.hi}{extra}"


def plan_slices(gh: GitHubClient, *, lo: int, hi: int | None = None, extra: str = "",
                cap: int = SEARCH_RESULT_CAP) -> list[Slice]:
    """[lo, hi] 를 결과가 cap 이하인 구간들로 나눈다. hi 가 없으면 가장 많은 스타를 상한으로 쓴다."""
    if hi is None:
        top = gh.search_repositories(f"stars:>={lo}{extra}", per_page=1)
        if top.total_count == 0 or not top.items:
            return []
        hi = top.items[0].stars
    out: list[Slice] = []

    def visit(a: int, b: int) -> None:
        total = gh.search_repositories(f"stars:{a}..{b}{extra}", per_page=1).total_count
        if total == 0:
            return
        if total <= cap:
            out.append(Slice(a, b, total))
        elif a == b:
            out.append(Slice(a, b, total, dense=True))
        else:
            mid = (a + b) // 2
            visit(a, mid)
            visit(mid + 1, b)

    visit(lo, hi)
    return out


def enumerate_slices(gh: GitHubClient, slices: list[Slice], extra: str = "", per_page: int = 100,
                     cap: int = SEARCH_RESULT_CAP) -> tuple[list[Repo], dict[str, Any]]:
    """구간마다 모든 쪽을 받는다.

    회귀(2026-10-26 첫 실제 실행, 641개 누락): 쪽이 덜 찼다고 멈추면 안 된다.
    Search 는 마지막 쪽이 아니어도 99개를 주거나, 시간 초과로 일부만 준다(incomplete_results).
    빈 쪽에서만 멈추고, 불완전한 쪽은 한 번 다시 받는다.
    """
    seen: dict[int, Repo] = {}
    gaps: list[dict[str, Any]] = []
    retries = 0
    for s in slices:
        q = slice_query(s, extra)
        ids: set[int] = set()
        for page in range(1, math.ceil(min(s.total, cap) / per_page) + 1):
            res = gh.search_repositories(q, page=page, per_page=per_page)
            if res.incomplete_results:
                retries += 1
                res = gh.search_repositories(q, page=page, per_page=per_page)
            if not res.items:
                break
            for r in res.items:
                seen.setdefault(r.id, r)
                ids.add(r.id)
        if not s.dense and len(ids) < s.total:
            gaps.append({"query": q, "expected": s.total, "found": len(ids)})
    stats = {
        "slices": len(slices),
        "expected": sum(s.total for s in slices),
        "found": len(seen),
        "dense_slices": sum(1 for s in slices if s.dense),
        "incomplete_retries": retries,
        "gaps": gaps,
    }
    return list(seen.values()), stats


def repair(gh: GitHubClient, slices: list[Slice], repos: list[Repo], *, extra: str = "",
           cap: int = SEARCH_RESULT_CAP, small: int = 100,
           min_gap: int = 5) -> tuple[list[Repo], dict[str, int]]:
    """받은 수가 기대보다 min_gap 이상 적은 구간을 small 이하로 다시 쪼개 한 쪽씩 받는다.

    같은 스타 수끼리는 요청마다 순서가 흔들려 쪽 경계에서 중복·누락이 생긴다.
    한 쪽에 다 들어가면 생기지 않는다.
    1~4개 차이는 열거하는 동안 스타가 바뀌어 구간을 넘나든 것일 수 있어 그대로 둔다.
    """
    by_id = {r.id: r for r in repos}
    before = len(by_id)
    repaired = 0
    for s in slices:
        if s.dense:
            continue
        have = sum(1 for r in by_id.values() if s.lo <= r.stars <= s.hi)
        if s.total - have < min_gap:
            continue
        subs = plan_slices(gh, lo=s.lo, hi=s.hi, extra=extra, cap=small)
        found, _ = enumerate_slices(gh, subs, extra=extra, cap=cap)
        for r in found:
            by_id.setdefault(r.id, r)
        repaired += 1
    return list(by_id.values()), {"repaired_slices": repaired, "recovered": len(by_id) - before}


def discover(gh: GitHubClient, *, today: date, pool_min: int = 1000, new_days: int = 30, new_min: int = 10,
             tracked: Iterable[str] = (), cap: int = SEARCH_RESULT_CAP,
             log: Callable[[str], None] = print) -> DiscoverResult:
    repos: dict[int, Repo] = {}
    sources: dict[int, list[str]] = {}

    def add(found: Iterable[Repo], source: str) -> None:
        for r in found:
            repos.setdefault(r.id, r)
            sources.setdefault(r.id, [])
            if source not in sources[r.id]:
                sources[r.id].append(source)

    log(f"후보군: 스타 ≥ {pool_min}")
    pool_slices = plan_slices(gh, lo=pool_min, cap=cap)
    pool, pool_stats = enumerate_slices(gh, pool_slices, cap=cap)
    pool, pool_stats["repair"] = repair(gh, pool_slices, pool, cap=cap)
    add(pool, "pool")

    since = (today - timedelta(days=new_days)).isoformat()
    extra = f" created:>={since}"
    log(f"새 저장소: {since} 이후 생성 · 스타 ≥ {new_min}")
    new_slices = plan_slices(gh, lo=new_min, extra=extra, cap=cap)
    new, new_stats = enumerate_slices(gh, new_slices, extra=extra, cap=cap)
    new, new_stats["repair"] = repair(gh, new_slices, new, extra=extra, cap=cap)
    add(new, "new")

    tracked = list(tracked)
    known = {r.full_name: r for r in repos.values()}
    missing: list[str] = []
    found_tracked: list[Repo] = []
    for name in tracked:
        if name in known:
            found_tracked.append(known[name])
            continue
        try:
            found_tracked.append(gh.get_repo(name))
        except GitHubError:
            missing.append(name)
    add(found_tracked, "tracked")

    rows = [
        SnapRow(id=r.id, full_name=r.full_name, stars=r.stars, forks=r.forks, open_issues=r.open_issues,
                created=r.created_at.date(), sources=tuple(sources[r.id]))
        for r in sorted(repos.values(), key=lambda x: x.id)
    ]
    stats = {
        "pool": pool_stats,
        "new": new_stats,
        "tracked": {"requested": len(tracked), "found": len(found_tracked), "missing": missing},
        "rows": len(rows),
    }
    return DiscoverResult(rows, stats)
