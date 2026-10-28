"""카테고리 추이 (SPEC FR-8.1, P2-7) — 코드로만 집계한다. LLM 0 · 네트워크 0 · 비용 0.

주마다 `data/weekly/<주>/categories.json` 을 쓴다:
- 카테고리별 그 주 스타 증가 합계(gain) · 증가한 AI 저장소 수(repos) · AI 탭 진입 수(entrants)
- **ALL** — 모든 AI 카테고리 합계
- 주 카테고리만 센다(보조 카테고리는 세지 않는다 — 두 번 세지 않게)
- 판정 기록의 카테고리 id 는 지금 분류 체계 id 로 옮겨 센다(FR-3.4). 모르는 id 는 unmapped 에 따로 둔다
- 판정 범위는 랭킹 후보뿐이다(결정 30). 그래서 판정이 끝난 저장소가 그 주 증가의 몇 %를 덮는지(coverage)와
  판정 전·거절·미분류(unclassified)의 크기를 함께 남긴다 — 합계를 "전체 AI 생태계"로 읽지 않게
"""

from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from startrend.core import io, week, weekfile
from startrend.core.taxonomy import Taxonomy
from startrend.core.weekfile import WeekRow

AXES = ("gain", "fresh", "growth", "total")
_NOTES = {
    "scope": "판정은 랭킹 후보만(결정 30) — 합계는 판정된 AI 저장소만. "
             "coverage 는 판정이 끝난 저장소가 그 주 증가에서 차지하는 비율",
    "rows": "주간 파일(증가 ≥ 10)의 행",
    "category": "주 카테고리만(보조 제외)",
}


def _zero(entrants: bool = True) -> dict[str, int]:
    return {"gain": 0, "repos": 0, "entrants": 0} if entrants else {"gain": 0, "repos": 0}


def aggregate_week(rows: Mapping[int, WeekRow], classified: Mapping[int, Mapping[str, Any]], tax: Taxonomy, *,
                   ai_entrants: set[int]) -> dict[str, Any]:
    cats = {cid: _zero() for cid in tax.ids()}
    all_ = _zero()
    non_ai, unclassified, unmapped = _zero(False), _zero(False), _zero(False)
    total = 0
    for rid, r in rows.items():
        total += r.gain
        c = classified.get(rid)
        if not c or c.get("status") != "ok":
            bucket = unclassified
        elif not c.get("is_ai"):
            bucket = non_ai
        else:
            cid = tax.current(c.get("category"))
            all_["gain"] += r.gain
            all_["repos"] += 1
            bucket = cats[cid] if cid else unmapped
        bucket["gain"] += r.gain
        bucket["repos"] += 1
    for rid in ai_entrants:
        c = classified.get(rid) or {}
        cid = tax.current(c.get("category"))
        all_["entrants"] += 1
        if cid:
            cats[cid]["entrants"] += 1
    decided = all_["gain"] + non_ai["gain"]
    return {"categories": cats, "ALL": all_, "non_ai": non_ai, "unclassified": unclassified,
            "unmapped": unmapped, "total_gain": total, "coverage": decided / total if total else None}


def _ai_entrants(data_dir: Path, w: date) -> set[int] | None:
    """그 주 AI 탭(4축)에 든 저장소. AI 탭이 아직 없으면(분류 전) None."""
    p = data_dir / "weekly" / week.week_name(w) / "rankings.json"
    if not p.exists():
        return None
    axes = io.read_json(p).get("axes", {})
    tabs = [axes.get(a, {}).get("ai") for a in AXES]
    if all(t is None for t in tabs):
        return None
    return {int(e["id"]) for t in tabs if t for e in t}


def categories_path(data_dir: Path, w: date) -> Path:
    return data_dir / "weekly" / week.week_name(w) / "categories.json"


def run_trends(*, data_dir: Path, weeks: Sequence[date], tax: Taxonomy,
               classified: Mapping[int, Mapping[str, Any]],
               log: Callable[[str], None] = print) -> dict[str, Any]:
    written = 0
    for w in weeks:
        entrants = _ai_entrants(data_dir, w)
        agg = aggregate_week(weekfile.read(weekfile.week_path(data_dir, w)), classified, tax,
                             ai_entrants=entrants or set())
        doc = {"week": week.week_name(w), "taxonomy_version": tax.version, "ai_tab": entrants is not None,
               **agg, "notes": _NOTES}
        if io.write_if_changed(categories_path(data_dir, w), io.dumps_json(doc)):
            written += 1
    return {"weeks": len(weeks), "written": written}


def series(data_dir: Path, weeks: Sequence[date], tax: Taxonomy) -> dict[str, Any]:
    """화면 선 그래프용 — 주 순서대로 카테고리(+ALL)별 gain·repos·entrants 열. 없는 주는 0."""
    names = [week.week_name(w) for w in weeks]
    docs = [io.read_json(categories_path(data_dir, w)) if categories_path(data_dir, w).exists() else {}
            for w in weeks]
    keys = ("gain", "repos", "entrants")

    def column(parts: list[Mapping[str, Any] | None]) -> dict[str, list[int]]:
        return {k: [int((p or {}).get(k, 0)) for p in parts] for k in keys}

    return {"weeks": names, "ALL": column([d.get("ALL") for d in docs]),
            "categories": {cid: column([(d.get("categories") or {}).get(cid) for d in docs])
                           for cid in tax.ids()}}
