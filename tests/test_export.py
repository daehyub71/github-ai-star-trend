"""stages.export — 사이트가 읽을 작은 파생 데이터 (FR-9, NFR-6, 결정 53). 비용 0.

- 공개 `data/site/`: index(주 목록·분류 체계) · weeks/<주>.json(랭킹 8개, 화면 필드만, 최근 12주 스파크라인) ·
  categories.json(카테고리+ALL × 주). 사이트 빌드는 data/stars 원시 시계열을 읽지 않는다(FR-9.2).
- 비공개 `.work/site-private/`: 최신 카드·주간 브리핑 사본 — 공개 저장소에 두지 않는다(결정 53).
- 정본에서 언제든 다시 만들 수 있고(FR-9.3), 내용이 바뀔 때만 쓴다.
"""

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from startrend.core import io, weekfile
from startrend.core.cards import CardStore
from startrend.core.weekfile import WeekRow
from startrend.stages import export as ex

W1, W2 = date(2026, 10, 11), date(2026, 10, 18)


def _entry(rid: int, name: str, **kw: Any) -> dict[str, Any]:
    return {"id": rid, "full_name": name, "description": "d" * 400, "language": "Python",
            "created": "2026-01-01", "stars_end": 5000, "gain": 900, "growth": 0.2, "start_stars": 4100,
            "rank": 1, "prev_rank": None,
            "is_ai": True, "type": "도구/라이브러리", "category": "rag", "secondary": None, "flags": [],
            "exact": True, "days": [1, 2, 3, 4, 5, 6, 7], "forks": 10, "open_issues": 3,
            "topics": ["a"] * 30, **kw}


def _data(tmp_path: Path) -> Path:
    data = tmp_path / "d"
    for k in range(12, -1, -1):                 # 13주 주간 파일 — o/a 는 매주, o/b 는 이번 주만
        w = W2 - timedelta(days=7 * k)
        rows = [WeekRow(1, "o/a", date(2026, 1, 1), 5000, 100 + k, False, None)]
        if k == 0:
            rows.append(WeekRow(2, "o/b", date(2026, 10, 1), 900, 800, True, (100,) * 7 + ()))
        weekfile.write(weekfile.week_path(data, w), rows)
    a, b = _entry(1, "o/a"), _entry(2, "o/b", is_ai=False, category=None, type="교육자료")
    for w, ai in ((W1, [a]), (W2, [a])):
        io.write_json(data / "weekly" / w.isoformat() / "rankings.json",
                      {"week": w.isoformat(), "week_end": (w + timedelta(days=6)).isoformat(),
                       "axes": {"gain": {"all": [a, b], "ai": ai}, "fresh": {"all": [b], "ai": None}},
                       "ai_status": {"gain": {"found": 1, "pending_above": 0}}})
    io.write_json(data / "weekly" / W2.isoformat() / "categories.json",
                  {"week": W2.isoformat(), "ALL": {"gain": 900, "repos": 1, "entrants": 1},
                   "coverage": 0.5, "categories": {"rag": {"gain": 900, "repos": 1, "entrants": 1}}})
    (data / "taxonomy.toml").write_text(
        'version = 2\ntypes = ["도구/라이브러리", "교육자료"]\n\n'
        '[[category]]\nid = "rag"\nname = "RAG·검색"\n'
        'desc = "x"\n\n[mapping]\n', encoding="utf-8")
    return data


def test_export_index_lists_weeks_and_taxonomy(tmp_path):
    data = _data(tmp_path)
    ex.run_export(data_dir=data, work_dir=tmp_path / "w", log=lambda m: None)
    idx = io.read_json(data / "site" / "index.json")
    assert idx["weeks"] == ["2026-10-11", "2026-10-18"] and idx["latest"] == "2026-10-18"
    assert idx["categories"] == [{"id": "rag", "name": "RAG·검색"}] and idx["taxonomy_version"] == 2


def test_export_week_keeps_only_screen_fields_and_adds_sparklines(tmp_path):
    data = _data(tmp_path)
    ex.run_export(data_dir=data, work_dir=tmp_path / "w", log=lambda m: None)
    wk = io.read_json(data / "site" / "weeks" / "2026-10-18.json")
    a = wk["axes"]["gain"]["ai"][0]
    assert set(a) == set(ex.ENTRY_FIELDS) | {"spark"}
    assert len(a["description"]) <= ex.DESC_CHARS and "topics" not in a and "forks" not in a
    assert a["spark"] == [111, 110, 109, 108, 107, 106, 105, 104, 103, 102, 101, 100]   # 오래된 주 → 이번 주
    b = wk["axes"]["gain"]["all"][1]
    assert b["spark"] == [0] * 11 + [800]            # 주간 파일에 없던 주는 증가 10 미만 → 0
    assert wk["axes"]["fresh"]["ai"] is None and wk["ai_status"]["gain"]["found"] == 1


def test_export_categories_series_follow_the_week_list(tmp_path):
    data = _data(tmp_path)
    ex.run_export(data_dir=data, work_dir=tmp_path / "w", log=lambda m: None)
    c = io.read_json(data / "site" / "categories.json")
    assert c["weeks"] == ["2026-10-11", "2026-10-18"]
    assert c["series"]["rag"]["gain"] == [None, 900] and c["series"]["ALL"]["gain"] == [None, 900]
    assert c["coverage"] == [None, 0.5] and c["names"]["ALL"] == "ALL"


def test_export_writes_only_when_content_changes(tmp_path):
    data = _data(tmp_path)
    first = ex.run_export(data_dir=data, work_dir=tmp_path / "w", log=lambda m: None)
    again = ex.run_export(data_dir=data, work_dir=tmp_path / "w", log=lambda m: None)
    assert first["written"] == 5 and again["written"] == 0       # index + 주 2개 + categories + repos


def _rank(w: date, axes: dict[str, Any]) -> dict[str, Any]:
    return {"week": w.isoformat(), "axes": axes}


def test_export_repos_counts_weeks_in_rising_ai_axes(tmp_path):
    # 저장소 추이(시안 v1.3) — AI 탭 뜨는 축(지금·새로·급성장)에 든 주를 센다.
    # 누적 TOP 축은 빼고(거대 저장소가 늘 낀다)
    a, b, c = _entry(1, "o/a"), _entry(2, "o/b", category="agent-skills"), _entry(3, "o/c")
    w0, w1, w2 = W2 - timedelta(days=14), W1, W2
    rankings = [
        (w0, _rank(w0, {"gain": {"all": [a], "ai": [a]}, "total": {"all": [c], "ai": [c]}})),
        (w1, _rank(w1, {"gain": {"all": [a], "ai": [a]}, "fresh": {"all": [a, b], "ai": [a, b]},
                        "total": {"all": [c], "ai": [c]}})),
        (w2, _rank(w2, {"growth": {"all": [b], "ai": [b]}, "gain": {"all": [a], "ai": None},
                        "total": {"all": [c], "ai": [c]}})),
    ]
    gains = {W2 - timedelta(days=7 * k): {2: 10 * (k + 1)} for k in range(12)}
    out = ex.repos_payload(rankings, gains)
    assert out["weeks"] == [w0.isoformat(), w1.isoformat(), w2.isoformat()]
    by = {r["full_name"]: r for r in out["repos"]}
    assert "o/c" not in by                                        # 누적 TOP 에만 든 저장소
    assert by["o/a"]["bits"] == "110" and by["o/a"]["streak"] == 0  # 한 주에 두 축이어도 한 번
    assert by["o/b"]["bits"] == "011" and by["o/b"]["streak"] == 2
    assert by["o/b"]["category"] == "agent-skills"
    assert by["o/b"]["spark"] == [120, 110, 100, 90, 80, 70, 60, 50, 40, 30, 20, 10]   # 마지막 주에 맞춘 12주
    assert by["o/b"]["gain4"] == 40 + 30 + 20 + 10
    assert by["o/a"]["spark"] == [0] * 12


def test_export_repos_drops_single_week_and_orders_by_weeks(tmp_path):
    a, b, c = _entry(1, "o/a"), _entry(2, "o/b"), _entry(3, "o/c")
    weeks = [W2 - timedelta(days=7 * k) for k in range(3, -1, -1)]
    lists = [[a, b, c], [a, b], [a, b], [b]]
    rankings = [(w, _rank(w, {"gain": {"all": [], "ai": ai}})) for w, ai in zip(weeks, lists, strict=True)]
    out = ex.repos_payload(rankings, {})
    assert [r["full_name"] for r in out["repos"]] == ["o/b", "o/a"]   # 4주 > 3주, 1주(o/c)는 뺀다
    assert set(out["repos"][0]) == {"id", "full_name", "category", "bits", "streak", "gain4", "spark"}


def test_export_repos_keeps_only_the_last_52_weeks(tmp_path):
    a = _entry(1, "o/a")
    weeks = [W2 - timedelta(days=7 * k) for k in range(59, -1, -1)]   # 60주
    out = ex.repos_payload([(w, _rank(w, {"gain": {"all": [], "ai": [a]}})) for w in weeks], {})
    assert len(out["weeks"]) == 52 and out["repos"][0]["bits"] == "1" * 52 and out["repos"][0]["streak"] == 52


def test_export_private_copies_cards_and_briefings_outside_data(tmp_path):
    # 결정 53 — 카드·브리핑은 공개 저장소(data/)에 쓰지 않는다
    data, work = _data(tmp_path), tmp_path / "w"
    store = CardStore(work / "cards")
    store.save(1, "---\nrepo: o/a\nrepo_id: 1\nas_of: 2026-10-24\n---\n# o/a\n", {"full_name": "o/a",
                                                                                 "as_of": "2026-10-24"})
    io.write_text_atomic(work / "2026-10-18" / "briefing.md", "# brief\n")
    stats = ex.run_export(data_dir=data, work_dir=work, log=lambda m: None)
    priv = work / "site-private"
    assert (priv / "cards" / "o__a.md").read_text(encoding="utf-8").startswith("---\nrepo: o/a")
    assert io.read_json(priv / "cards" / "index.json") == [{"repo_id": 1, "full_name": "o/a",
                                                             "as_of": "2026-10-24", "slug": "o__a"}]
    assert (priv / "briefings" / "2026-10-18.md").exists()
    assert stats["private_cards"] == 1 and stats["private_briefings"] == 1
    assert not any(p.suffix == ".md" for p in (data / "site").rglob("*"))


def test_export_site_files_stay_small(tmp_path):
    data = _data(tmp_path)
    ex.run_export(data_dir=data, work_dir=tmp_path / "w", log=lambda m: None)
    for p in (data / "site").rglob("*.json"):
        assert p.stat().st_size < 1_048_576
        json.loads(p.read_text(encoding="utf-8"))
