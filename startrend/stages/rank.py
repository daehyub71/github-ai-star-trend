"""랭킹 (SPEC FR-4, 결정 28) — 주간 파일 하나로 그 주의 4축 랭킹을 만든다. 비용 0.

축: gain(지난 주 증가량) · fresh(생성 30일 이내, 누적 스타순)
    · growth(증가 ÷ 주 시작 스타, 시작 ≥ 1,000) · total(누적).
급등 패턴은 근거 수치를 붙여 표시만 한다 — 어느 축에서도 빼지 않는다(MEASURE §5: 출시 급등을 오탐하는 사례).
AI 탭은 Phase 2 분류 뒤에 채운다(지금은 null).
랭킹 파일은 파생 데이터라 다시 만들 수 있다(내용이 바뀔 때만 쓴다) — 주간 스타 파일과 달리 불변이 아니다.
"""

from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from startrend.clients.github import GitHubClient, GitHubError
from startrend.clients.github_parse import GitHubFormatError
from startrend.core import io, meta, week, weekfile
from startrend.core.weekfile import WeekRow

AXES = ("gain", "fresh", "growth", "total")
TOP = 15
POOL = 200  # 축마다 남기는 후보 순서 — classify 가 AI 15개를 채울 때까지 내려간다(결정 30)
FRESH_DAYS = 30
MIN_START = 1000

# 급등 패턴 표시 기준 — 표시만 한다 (결정 28). 근거: MEASURE §5
PEAK_MIN_GAIN = 1000
PEAK_SHARE = 0.5          # 하루에 주간 증가의 50% 이상
SAME_OWNER_MIN = 3        # 같은 계정의 30일 이내 새 저장소(스타 ≥ 1,000) 3개 이상
ISSUE_RATIO = 0.03        # 열린 이슈 / 스타 3% 이상 (보통 1% 미만)
FORK_RATIO = 0.30         # 포크 / 스타 30% 이상
# 휴면 후 폭증 (결정 40) — 오래된 저장소가 4주 만에 몇 배로. 근거: MEASURE §13
DORMANT_WEEKS = 4         # 이번 주 포함 4주 창
DORMANT_MIN_AGE = 60      # 생성 60일 이상 (새 저장소는 원래 폭발적으로 큰다)
DORMANT_MAX_START = 5000  # 4주 전 스타 5,000 미만
DORMANT_MULT = 10         # 4주 동안 10배 이상


def rankings_path(data_dir: Path, week_start: date) -> Path:
    return data_dir / "weekly" / week.week_name(week_start) / "rankings.json"


def _is_fresh(r: WeekRow, week_end: date) -> bool:
    return (week_end - r.created).days < FRESH_DAYS


def compute_axes(rows: dict[int, WeekRow], week_start: date, *, top: int = TOP,
                 extra_totals: dict[int, WeekRow] | None = None) -> dict[str, list[WeekRow]]:
    week_end = week.week_end(week_start)
    rs = list(rows.values())
    growth = [r for r in rs if r.stars_end - r.gain >= MIN_START]
    totals = {**(extra_totals or {}), **rows}
    return {
        "gain": sorted(rs, key=lambda r: (-r.gain, r.id))[:top],
        "fresh": sorted((r for r in rs if _is_fresh(r, week_end)), key=lambda r: (-r.stars_end, r.id))[:top],
        "growth": sorted(growth, key=lambda r: (-r.gain / (r.stars_end - r.gain), r.id))[:top],
        "total": sorted(totals.values(), key=lambda r: (-r.stars_end, r.id))[:top],
    }


def prior_gains(data_dir: Path, week_start: date, weeks: int = DORMANT_WEEKS - 1) -> dict[int, int] | None:
    """지난 weeks 주의 증가 합(저장소별). 그 주 파일이 하나라도 없으면 None — 창을 채울 수 없다.

    주간 파일에 없는 저장소는 그 주 증가가 10 미만이었다 — 0 으로 본다(4주 전 스타를 조금 크게 잡는 쪽).
    """
    total: dict[int, int] = {}
    for k in range(1, weeks + 1):
        p = weekfile.week_path(data_dir, week_start - timedelta(days=7 * k))
        if not p.exists():
            return None
        for rid, r in weekfile.read(p).items():
            total[rid] = total.get(rid, 0) + r.gain
    return total


def flags_for(r: WeekRow, rows: dict[int, WeekRow], info: dict[str, int] | None, week_start: date,
              *, prior_gain: int | None = None) -> list[dict[str, Any]]:
    """prior_gain: 지난 3주의 증가 합. None 이면 휴면 후 폭증은 판단하지 않는다."""
    flags: list[dict[str, Any]] = []
    if r.days and r.gain >= PEAK_MIN_GAIN:
        share = max(r.days) / r.gain
        if share >= PEAK_SHARE:
            pct = round(share * 100)
            flags.append({"kind": "peak_day", "label": f"하루 몰림 {pct}%", "value": pct})
    week_end = week.week_end(week_start)
    owner = r.full_name.split("/", 1)[0]
    same = [x for x in rows.values()
            if x.full_name.split("/", 1)[0] == owner and _is_fresh(x, week_end) and x.stars_end >= 1000]
    if len(same) >= SAME_OWNER_MIN and r in same:
        n = len(same)
        flags.append({"kind": "same_owner_new", "label": f"같은 계정 새 저장소 {n}개", "value": n})
    if prior_gain is not None and (week_end - r.created).days >= DORMANT_MIN_AGE:
        start = r.stars_end - r.gain - prior_gain  # 4주 전 스타
        if (start < DORMANT_MAX_START and r.gain + prior_gain >= PEAK_MIN_GAIN
                and r.stars_end >= DORMANT_MULT * max(start, 1)):
            mult = r.stars_end / max(start, 1)
            flags.append({"kind": "dormant_burst", "label": f"잠잠하다 4주 만에 {mult:,.0f}배",
                          "value": round(mult, 1)})
    if info:
        stars = info.get("stars") or r.stars_end
        if stars >= 1000:
            issues = info.get("open_issues", 0) / stars
            forks = info.get("forks", 0) / stars
            if issues >= ISSUE_RATIO:
                flags.append({"kind": "issue_ratio", "label": f"열린 이슈 {issues * 100:.1f}%",
                              "value": round(issues * 100, 1)})
            if forks >= FORK_RATIO:
                flags.append({"kind": "fork_ratio", "label": f"포크 {forks * 100:.1f}%",
                              "value": round(forks * 100, 1)})
    return flags


def _prev_ranks(data_dir: Path, week_start: date) -> dict[str, dict[int, int]]:
    p = rankings_path(data_dir, week_start - timedelta(days=7))
    if not p.exists():
        return {}
    axes = io.read_json(p).get("axes", {})
    return {a: {e["id"]: e["rank"] for e in (axes.get(a, {}).get("all") or [])} for a in AXES}


def run_rank(gh: GitHubClient, *, week_start: date, data_dir: Path, top: int = TOP, pool: int = POOL,
             extra_totals: dict[int, WeekRow] | None = None,
             log: Callable[[str], None] = print) -> dict[str, Any]:
    wname = week.week_name(week_start)
    rows = weekfile.read(weekfile.week_path(data_dir, week_start))
    axes = compute_axes(rows, week_start, top=top, extra_totals=extra_totals)
    entrants = {r.id: r for rs in axes.values() for r in rs}

    infos: dict[int, dict[str, Any]] = {}
    calls = 0
    for rid, r in sorted(entrants.items()):
        try:
            repo = gh.get_repo(r.full_name)
            calls += 1
        except (GitHubError, GitHubFormatError):
            log(f"  ! 저장소 정보 없음: {r.full_name}")
            continue
        infos[rid] = {"description": repo.description, "topics": list(repo.topics), "language": repo.language,
                      "forks": repo.forks, "open_issues": repo.open_issues, "stars": repo.stars,
                      "full_name": repo.full_name}
        old = meta.load(data_dir, rid) or {}
        first = min(filter(None, [old.get("first_seen"), wname]))
        last = max(filter(None, [old.get("last_seen"), wname]))
        meta.save(data_dir, {
            "id": rid, "full_name": repo.full_name, "description": repo.description,
            "topics": list(repo.topics), "language": repo.language, "created": r.created.isoformat(),
            "first_seen": first, "last_seen": last,
        })

    prev = _prev_ranks(data_dir, week_start)
    prior = prior_gains(data_dir, week_start)
    out_axes: dict[str, dict[str, Any]] = {}
    for a, rs in axes.items():
        entries = []
        for i, r in enumerate(rs, 1):
            info = infos.get(r.id, {})
            start = r.stars_end - r.gain
            entries.append({
                "rank": i, "id": r.id, "full_name": info.get("full_name", r.full_name),
                "description": info.get("description"), "language": info.get("language"),
                "topics": info.get("topics", []), "created": r.created.isoformat(),
                "stars_end": r.stars_end, "gain": r.gain, "start_stars": start,
                "growth": round(r.gain / start, 4) if start > 0 else None,
                "exact": r.exact, "days": list(r.days) if r.days else None,
                "forks": info.get("forks"), "open_issues": info.get("open_issues"),
                "flags": flags_for(r, rows, info or None, week_start,
                                   prior_gain=None if prior is None else prior.get(r.id, 0)),
                "prev_rank": prev.get(a, {}).get(r.id),
            })
        out_axes[a] = {"all": entries, "ai": None}
    doc = {
        "week": wname, "week_end": week.week_end(week_start).isoformat(), "top": top, "axes": out_axes,
        "notes": {"total": "주간 파일(증가 ≥ 10)과 스냅샷이 있으면 그 값 기준",
                  "ai": "Phase 2 분류 뒤에 채운다",
                  "pool": f"축마다 상위 {pool}개 ID — classify 가 위에서부터 AI 15개까지 판정(결정 30)"},
        "pool": {a: [r.id for r in rs]
                 for a, rs in compute_axes(rows, week_start, top=pool, extra_totals=extra_totals).items()},
    }
    path = rankings_path(data_dir, week_start)
    written = io.write_if_changed(path, io.dumps_json(doc))
    return {"week": wname, "entrants": len(entrants), "repo_calls": calls, "written": written,
            "path": str(path)}


def tracked_names(data_dir: Path, week_start: date) -> list[str]:
    """그 주 랭킹에 든 저장소 이름 — 다음 주 discover 의 추적 목록(FR-1.1 ③)."""
    p = rankings_path(data_dir, week_start)
    if not p.exists():
        return []
    axes = io.read_json(p)["axes"]
    return sorted({e["full_name"] for a in axes.values() for e in (a.get("all") or [])})
