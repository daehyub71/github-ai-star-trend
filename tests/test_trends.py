"""stages.trends — 카테고리 추이 (FR-8.1, P2-7). 코드로만 집계한다 — LLM 0, 네트워크 0."""

from datetime import date
from pathlib import Path
from typing import Any

from startrend.core import io, weekfile
from startrend.core import taxonomy as tx
from startrend.core.weekfile import WeekRow
from startrend.stages import trends as tr

ROOT = Path(__file__).resolve().parents[1]
TAX = tx.load(ROOT / "data" / "taxonomy.toml")
W1, W2 = date(2026, 10, 11), date(2026, 10, 18)
OLD = date(2020, 1, 1)


def row(rid: int, gain: int) -> WeekRow:
    return WeekRow(rid, f"o/r{rid}", OLD, 10_000 + gain, gain, False, None)


def ok(ai: bool, cat: str | None = None) -> dict[str, Any]:
    return {"status": "ok", "is_ai": ai, "type": "도구/라이브러리", "category": cat if ai else None}


ROWS = {1: row(1, 100), 2: row(2, 50), 3: row(3, 30), 4: row(4, 500), 5: row(5, 70), 6: row(6, 5)}
CLASSIFIED = {1: ok(True, "rag"), 2: ok(True, "rag"), 3: ok(True, "mcp-tools"), 4: ok(False),
              6: {"status": "refused"}}


def test_trends_week_sums_gain_and_repos_by_category_with_all():
    out = tr.aggregate_week(ROWS, CLASSIFIED, TAX, ai_entrants={1, 3})
    assert out["categories"]["rag"] == {"gain": 150, "repos": 2, "entrants": 1}
    assert out["categories"]["mcp-tools"] == {"gain": 30, "repos": 1, "entrants": 1}
    # 0 도 남긴다 — 선 그래프가 끊기지 않게
    assert out["categories"]["coding-agent"] == {"gain": 0, "repos": 0, "entrants": 0}
    assert out["ALL"] == {"gain": 180, "repos": 3, "entrants": 2}
    assert out["non_ai"] == {"gain": 500, "repos": 1}
    # 판정 전(5)과 거절·미분류(6)는 어느 카테고리에도 넣지 않는다 — 대신 크기를 남긴다
    assert out["unclassified"] == {"gain": 75, "repos": 2}


def test_trends_coverage_is_the_share_of_gain_with_a_final_decision():
    # 판정 범위는 랭킹 후보뿐이다(결정 30) — 합계가 그 주 증가의 몇 %를 덮는지 함께 남긴다
    out = tr.aggregate_week(ROWS, CLASSIFIED, TAX, ai_entrants=set())
    assert out["total_gain"] == 755
    assert abs(out["coverage"] - 680 / 755) < 1e-9


def test_trends_follow_renamed_categories(tmp_path):
    p = tmp_path / "taxonomy.toml"
    p.write_text('version = 2\ntypes = ["도구/라이브러리"]\n'
                 '[[category]]\nid = "new"\nname = "새"\ndesc = "x"\n'
                 '[mapping]\n"v1:old" = "new"\n', encoding="utf-8")
    t2 = tx.load(p)
    out = tr.aggregate_week({1: row(1, 40)}, {1: ok(True, "old")}, t2, ai_entrants=set())
    assert out["categories"]["new"]["gain"] == 40 and out["unmapped"] == {"gain": 0, "repos": 0}


def test_trends_unknown_category_is_kept_aside_not_dropped():
    out = tr.aggregate_week({1: row(1, 40)}, {1: ok(True, "quantum-ai")}, TAX, ai_entrants=set())
    assert out["unmapped"] == {"gain": 40, "repos": 1} and out["ALL"]["gain"] == 40


def _write_week(data_dir: Path, w: date, rows: dict[int, WeekRow], ai: list[int] | None) -> None:
    weekfile.write(weekfile.week_path(data_dir, w), list(rows.values()))
    axes = {a: {"all": [], "ai": None if ai is None else [{"id": i} for i in ai]}
            for a in ("gain", "fresh", "growth", "total")}
    io.write_json(data_dir / "weekly" / w.isoformat() / "rankings.json",
                  {"week": w.isoformat(), "axes": axes})


def test_trends_run_writes_one_file_per_week_and_notes_a_missing_ai_tab(tmp_path):
    _write_week(tmp_path, W1, ROWS, ai=None)            # 분류 전 주
    _write_week(tmp_path, W2, ROWS, ai=[1, 3])
    stats = tr.run_trends(data_dir=tmp_path, weeks=[W1, W2], tax=TAX, classified=CLASSIFIED)
    a = io.read_json(tmp_path / "weekly" / "2026-10-11" / "categories.json")
    b = io.read_json(tmp_path / "weekly" / "2026-10-18" / "categories.json")
    assert a["ai_tab"] is False and a["ALL"]["entrants"] == 0
    assert b["ai_tab"] is True and b["ALL"]["entrants"] == 2 and b["taxonomy_version"] == TAX.version
    assert stats["weeks"] == 2 and stats["written"] == 2


def test_trends_series_lines_up_weeks_for_the_chart(tmp_path):
    _write_week(tmp_path, W1, {1: row(1, 10)}, ai=[1])
    _write_week(tmp_path, W2, ROWS, ai=[1, 3])
    tr.run_trends(data_dir=tmp_path, weeks=[W1, W2], tax=TAX, classified=CLASSIFIED)
    s = tr.series(tmp_path, [W1, W2], TAX)
    assert s["weeks"] == ["2026-10-11", "2026-10-18"]
    assert s["ALL"]["gain"] == [10, 180] and s["categories"]["rag"]["gain"] == [10, 150]
    assert s["categories"]["mcp-tools"]["entrants"] == [0, 1]


def test_trends_run_is_deterministic(tmp_path):
    _write_week(tmp_path, W2, ROWS, ai=[1, 3])
    first = tr.run_trends(data_dir=tmp_path, weeks=[W2], tax=TAX, classified=CLASSIFIED)
    again = tr.run_trends(data_dir=tmp_path, weeks=[W2], tax=TAX, classified=CLASSIFIED)
    assert first["written"] == 1 and again["written"] == 0            # 내용이 같으면 다시 쓰지 않는다
