"""사이트 파생 데이터 내보내기 (SPEC FR-9, NFR-6, 결정 53) — 비용 0, 정본에서 언제든 다시 만든다(FR-9.3).

공개 `data/site/` (커밋):
- `index.json` — 주 목록·최신 주·분류 체계 이름
- `weeks/<주>.json` — 랭킹 8개(4축 × 전체·AI 탭). 화면에 쓰는 필드만 + 최근 12주 스파크라인(FR-9.1)
- `categories.json` — 카테고리(+ALL) × 주의 증가·저장소 수·AI 탭 진입 수와 커버리지

사이트 빌드는 `data/stars/` 원시 시계열을 읽지 않는다(FR-9.2) — 스파크라인은 여기서 미리 계산한다.

비공개 `.work/site-private/` (커밋하지 않음 — 결정 53): 최신 카드(보관소)와 주간 브리핑의 사본.
사이트는 이 폴더가 있으면 카드·브리핑을 보여 주고, 없으면 그 자리를 비운다. 배포 때 어디서 가져올지는 Phase 5.
"""

import json
import tomllib
from collections.abc import Callable, Mapping
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from startrend.core import cards, io, week, weekfile

ENTRY_FIELDS = ("id", "full_name", "description", "language", "created", "stars_end", "gain", "growth",
                "start_stars", "rank", "prev_rank", "is_ai", "type", "category", "secondary", "flags",
                "exact", "days")
DESC_CHARS = 160
SPARK_WEEKS = 12


def _dump(obj: Any) -> str:
    """사이트 파일은 기계만 읽는다 — 들여쓰기 없이(52주 6.5MB → 커밋당 5MB 가드 안). 키 순서는 고정."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def site_dir(data_dir: Path) -> Path:
    return data_dir / "site"


def private_dir(work_dir: Path) -> Path:
    return work_dir / "site-private"


def _weeks(data_dir: Path) -> list[date]:
    return sorted(week.parse_week(p.parent.name) for p in (data_dir / "weekly").glob("*/rankings.json"))


def _gains(data_dir: Path) -> dict[date, dict[int, int]]:
    out: dict[date, dict[int, int]] = {}
    for p in sorted((data_dir / "stars").glob("*/*.csv")):
        out[week.parse_week(p.stem)] = {rid: r.gain for rid, r in weekfile.read(p).items()}
    return out


def _entry(e: Mapping[str, Any], spark: list[int]) -> dict[str, Any]:
    out = {k: e.get(k) for k in ENTRY_FIELDS}
    desc = " ".join(str(e.get("description") or "").split())
    out["description"] = desc if len(desc) <= DESC_CHARS else desc[:DESC_CHARS - 1] + "…"
    if not e.get("exact"):
        out["days"] = None
    out["spark"] = spark
    return out


def week_payload(ranking: Mapping[str, Any], w: date,
                 gains: Mapping[date, Mapping[int, int]]) -> dict[str, Any]:
    span = [w - timedelta(days=7 * k) for k in range(SPARK_WEEKS - 1, -1, -1)]   # 오래된 주 → 이번 주

    def spark(rid: int) -> list[int]:
        # 주간 파일에 없던 주는 증가가 10 미만이었다 — 0 으로 둔다
        return [int(gains.get(x, {}).get(rid, 0)) for x in span]

    axes: dict[str, Any] = {}
    for axis, tabs in (ranking.get("axes") or {}).items():
        axes[axis] = {tab: (None if rows is None else [_entry(e, spark(int(e["id"]))) for e in rows])
                      for tab, rows in tabs.items()}
    return {"week": w.isoformat(), "week_end": week.week_end(w).isoformat(), "axes": axes,
            "ai_status": ranking.get("ai_status")}


def categories_payload(data_dir: Path, weeks: list[date], names: Mapping[str, str]) -> dict[str, Any]:
    per_week = []
    for w in weeks:
        p = data_dir / "weekly" / week.week_name(w) / "categories.json"
        per_week.append(io.read_json(p) if p.exists() else None)
    ids = sorted({c for d in per_week if d for c in (d.get("categories") or {})})
    out: dict[str, Any] = {}
    for cid in [*ids, "ALL"]:
        out[cid] = {k: [(_node(d, cid).get(k, 0) if d else None) for d in per_week]
                    for k in ("gain", "repos", "entrants")}
    return {"weeks": [week.week_name(w) for w in weeks], "series": out,
            "coverage": [d.get("coverage") if d else None for d in per_week],
            "names": {**{c: names.get(c, c) for c in ids}, "ALL": "ALL"}}


def _node(d: Mapping[str, Any], cid: str) -> Mapping[str, Any]:
    node = d.get("ALL") if cid == "ALL" else (d.get("categories") or {}).get(cid)
    return node or {}


def _taxonomy(data_dir: Path) -> dict[str, Any]:
    p = data_dir / "taxonomy.toml"
    if not p.exists():
        return {"version": None, "category": []}
    with p.open("rb") as f:
        return tomllib.load(f)


def _private(work_dir: Path) -> tuple[int, int]:
    """보관소의 최신 카드와 주간 브리핑을 비공개 폴더로 옮겨 적는다(결정 53)."""
    out = private_dir(work_dir)
    store = cards.CardStore(work_dir / "cards")
    index = []
    for meta_path in sorted((work_dir / "cards").glob("*.json")) if (work_dir / "cards").exists() else []:
        if not meta_path.stem.isdigit():
            continue
        stored = store.load(int(meta_path.stem))
        if stored is None:
            continue
        name = str(stored.meta.get("full_name") or cards.front(stored.markdown).get("repo", ""))
        slug = name.replace("/", "__")
        io.write_if_changed(out / "cards" / f"{slug}.md", stored.markdown)
        index.append({"repo_id": int(meta_path.stem), "full_name": name,
                      "as_of": stored.meta.get("as_of"), "slug": slug})
    if index:
        io.write_if_changed(out / "cards" / "index.json", io.dumps_json(index))
    briefings = 0
    for p in sorted(work_dir.glob("*/briefing.md")):
        io.write_if_changed(out / "briefings" / f"{p.parent.name}.md", io.read_text(p))
        briefings += 1
    return len(index), briefings


def run_export(*, data_dir: Path, work_dir: Path, log: Callable[[str], None] = print) -> dict[str, Any]:
    weeks = _weeks(data_dir)
    tax = _taxonomy(data_dir)
    names = {c["id"]: c["name"] for c in tax.get("category") or []}
    gains = _gains(data_dir)
    site = site_dir(data_dir)
    written = 0
    index = {"weeks": [week.week_name(w) for w in weeks],
             "latest": week.week_name(weeks[-1]) if weeks else None,
             "taxonomy_version": tax.get("version"), "types": tax.get("types") or [],
             "categories": [{"id": c["id"], "name": c["name"]} for c in tax.get("category") or []]}
    written += io.write_if_changed(site / "index.json", _dump(index))
    for w in weeks:
        ranking = io.read_json(data_dir / "weekly" / week.week_name(w) / "rankings.json")
        written += io.write_if_changed(site / "weeks" / f"{week.week_name(w)}.json",
                                       _dump(week_payload(ranking, w, gains)))
    written += io.write_if_changed(site / "categories.json",
                                   _dump(categories_payload(data_dir, weeks, names)))
    n_cards, n_briefs = _private(work_dir)
    log(f"  사이트 데이터: 주 {len(weeks)}개 · 바뀐 파일 {written}개 · "
        f"비공개 카드 {n_cards} · 브리핑 {n_briefs}")
    return {"weeks": len(weeks), "written": written, "private_cards": n_cards, "private_briefings": n_briefs}
