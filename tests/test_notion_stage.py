"""notion 단계 (SPEC FR-15, NFR-16) — MockNotion 으로 네트워크 0.

핵심 회귀: 상태가 "초안"이 아닌 페이지는 고치지 않는다(R24). 사용자가 검토하며 고친 것을 덮어쓰지 않는다.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from startrend.clients.notion import MockNotion, NotionError
from startrend.stages import notion as nt

W = "2026-10-18"


def _entry(i: int, name: str, cat: str | None = "rag", **over: Any) -> dict[str, Any]:
    e = {"id": i, "full_name": name, "category": cat, "type": "도구/라이브러리", "stars_end": 10_000 + i,
         "gain": 5_000 - i, "growth": 0.25, "start_stars": 8_000, "created": "2025-01-01", "rank": i,
         "description": f"{name} desc", "is_ai": True}
    e.update(over)
    return e


def _src(tmp: Path) -> tuple[Path, Path]:
    site, priv = tmp / "site", tmp / "priv"
    (site / "weeks").mkdir(parents=True)
    (priv / "cards").mkdir(parents=True)
    (priv / "briefings").mkdir()
    (site / "index.json").write_text(json.dumps({
        "weeks": ["2026-10-11", W], "latest": W, "taxonomy_version": 2, "types": ["도구/라이브러리", "기타"],
        "categories": [{"id": "rag", "name": "RAG·검색"}, {"id": "mcp-tools", "name": "MCP 서버·도구"}]},
        ensure_ascii=False), encoding="utf-8")
    prev = {"week": "2026-10-11", "week_end": "2026-10-17",
            "axes": {"gain": {"all": [_entry(1, "o/a")], "ai": [_entry(1, "o/a")]}}}
    cur = {"week": W, "week_end": "2026-10-24", "axes": {
        "gain": {"all": [_entry(1, "o/a"), _entry(9, "x/no")],
                 "ai": [_entry(1, "o/a"), _entry(2, "o/b", "mcp-tools")]},
        "fresh": {"all": [], "ai": [_entry(3, "o/c")]},
        "growth": {"all": [], "ai": [_entry(2, "o/b", "mcp-tools")]},
        "total": {"all": [], "ai": None}}}
    for d in (prev, cur):
        (site / "weeks" / f"{d['week']}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    refs = []
    for i, name in ((1, "o/a"), (2, "o/b"), (7, "z/other")):
        slug = name.replace("/", "__")
        (priv / "cards" / f"{slug}.md").write_text(
            f"---\nrepo: {name}\nrepo_id: {i}\nweek: {W}\nas_of: 2026-10-24\n---\n# {name}\n\n"
            f"## ① 3줄 요약\n- **무엇인지** — {name} 는 도구다.\n- **왜 지금 떴나** — 릴리스.\n"
            f"- **어떤 의미인지** — 의미.\n", encoding="utf-8")
        refs.append({"repo_id": i, "full_name": name, "as_of": "2026-10-24", "slug": slug})
    (priv / "cards" / "index.json").write_text(json.dumps(refs), encoding="utf-8")
    (priv / "briefings" / f"{W}.md").write_text(
        f"---\nweek: {W}\n---\n# 이번 주 AI 트렌드 — {W} ~ 2026-10-24\n\n"
        "헤드라인 한 줄이다.\n\n## 시사점\n- 하나\n",
        encoding="utf-8")
    return site, priv


@pytest.fixture
def ready(tmp_path: Path) -> tuple[MockNotion, dict[str, Any], nt.WeekDoc]:
    site, priv = _src(tmp_path)
    wd = nt.load_week(site, priv, W)
    mock = MockNotion()
    idx = nt.setup(mock, "parent-1", nt.empty_index(), names=wd.names, types=wd.types)
    return mock, idx, wd


def _publish(mock: MockNotion, idx: dict[str, Any], wd: nt.WeekDoc) -> tuple[dict[str, Any], list[str]]:
    logs: list[str] = []
    stats = nt.publish_week(mock, idx, wd, save=lambda i: None, log=logs.append)
    return stats, logs


def test_notion_setup_creates_three_databases_with_status_and_relation(ready):
    mock, idx, _ = ready
    assert [mock.titles[ds] for ds in mock.schemas] == ["주간", "저장소 카드", "블로그 초안"]
    assert set(mock.parents.values()) == {"parent-1"} and idx["parent_page_id"] == "parent-1"
    for ds in mock.schemas.values():
        opts = [(o["name"], o["group"]) for o in ds["상태"]["status"]["options"]]
        assert opts == [("초안", "To-do"), ("검토 중", "In progress"), ("승인", "In progress"),
                        ("게시됨", "Complete")]
    blog = mock.schemas[idx["databases"]["blog"]["data_source_id"]]
    assert blog["주"]["relation"]["data_source_id"] == idx["databases"]["weekly"]["data_source_id"]
    cards = mock.schemas[idx["databases"]["cards"]["data_source_id"]]
    assert {o["name"] for o in cards["카테고리"]["select"]["options"]} == {"RAG·검색", "MCP 서버·도구"}


def test_notion_setup_refuses_to_run_twice(ready):
    mock, idx, wd = ready
    with pytest.raises(nt.NotionStageError):
        nt.setup(mock, "parent-1", idx, names=wd.names, types=wd.types)


def test_notion_week_doc_reads_cards_of_the_weeks_ai_tabs(ready):
    _, _, wd = ready
    assert [c.full_name for c in wd.cards] == ["o/a", "o/b"]          # 카드 없는 o/c · 다른 주 z/other 제외
    assert wd.ai_count == 3 and wd.headline == "헤드라인 한 줄이다."
    a = wd.cards[0]
    assert a.first_week == "2026-10-11" and wd.cards[1].first_week == W
    assert a.entry["gain"] == 4_999


def test_notion_publish_creates_card_pages_then_week_page_with_links(ready):
    mock, idx, wd = ready
    stats, _ = _publish(mock, idx, wd)
    assert stats["created"] == 3 and stats["updated"] == 0
    assert [w for w in mock.writes() if w[0] != "create_database"] == [
        ("create_page", "page-1"), ("create_page", "page-2"), ("create_page", "page-3")]
    card = mock.pages[idx["cards"]["1"]["page_id"]]
    assert card.properties["저장소"]["title"][0]["text"]["content"] == "o/a"
    assert card.properties["카테고리"] == {"select": {"name": "RAG·검색"}}
    assert card.properties["누적 스타"] == {"number": 10_001}
    assert card.properties["지난 주 증가"] == {"number": 4_999}
    assert card.properties["처음 등장 주"] == {"date": {"start": "2026-10-11"}}
    assert card.properties["상태"] == {"status": {"name": "초안"}}
    assert not card.markdown.startswith("---") and "# o/a" not in card.markdown
    assert "① 3줄 요약" in card.markdown
    week = mock.pages[idx["weeks"][W]["page_id"]]
    assert week.properties["랭킹 진입 수"] == {"number": 3}
    assert week.properties["헤드라인"]["rich_text"][0]["text"]["content"] == "헤드라인 한 줄이다."
    assert week.properties["사이트"] == {"url": f"https://github-ai-star-trend.vercel.app/week/{W}"}
    assert idx["cards"]["1"]["url"] in week.markdown and idx["cards"]["2"]["url"] in week.markdown
    assert "지금 뜨는 저장소" in week.markdown and "[o/a](https://github.com/o/a)" in week.markdown
    assert "AI 작성" in week.markdown and "## 시사점" in week.markdown


def test_notion_publish_again_updates_draft_pages(ready):
    mock, idx, wd = ready
    _publish(mock, idx, wd)
    before = len(mock.pages)
    stats, _ = _publish(mock, idx, wd)
    assert stats["created"] == 0 and stats["updated"] == 3 and len(mock.pages) == before
    assert ("replace_markdown", idx["weeks"][W]["page_id"]) in mock.writes()
    assert mock.pages[idx["cards"]["1"]["page_id"]].properties["상태"] == {"status": {"name": "초안"}}


def test_notion_publish_leaves_reviewed_pages_alone(ready):
    # NFR-16 · R24 — 사용자가 검토를 시작한 페이지는 속성도 본문도 건드리지 않는다
    mock, idx, wd = ready
    _publish(mock, idx, wd)
    card, week = idx["cards"]["1"]["page_id"], idx["weeks"][W]["page_id"]
    mock.user_sets(card, "상태", {"status": {"name": "검토 중"}})
    mock.user_sets(week, "상태", {"status": {"name": "게시됨"}})
    mock.pages[card].markdown = "사용자가 고친 글"
    n = len(mock.writes())
    stats, logs = _publish(mock, idx, wd)
    touched = {pid for _, pid in mock.writes()[n:]}
    assert card not in touched and week not in touched
    assert mock.pages[card].markdown == "사용자가 고친 글"
    assert stats["kept"] == 2 and stats["updated"] == 1
    assert any("검토 중" in m and "o/a" in m for m in logs)


def test_notion_publish_skips_trashed_or_missing_pages(ready):
    mock, idx, wd = ready
    _publish(mock, idx, wd)
    mock.user_trashes(idx["cards"]["1"]["page_id"])
    del mock.pages[idx["cards"]["2"]["page_id"]]
    n = len(mock.pages)
    stats, logs = _publish(mock, idx, wd)
    assert stats["kept"] == 2 and len(mock.pages) == n              # 다시 만들지 않는다
    assert sum("휴지통" in m or "없다" in m for m in logs) == 2


def test_notion_publish_saves_the_index_after_each_page(ready):
    mock, idx, wd = ready
    saved: list[int] = []
    real = mock.create_page
    calls = {"n": 0}

    def flaky(*a: Any, **k: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 2:
            raise NotionError("boom", 503)
        return real(*a, **k)

    mock.create_page = flaky  # type: ignore[method-assign,unused-ignore]
    with pytest.raises(NotionError):
        nt.publish_week(mock, idx, wd, save=lambda i: saved.append(len(i["cards"])), log=lambda m: None)
    assert saved == [1] and list(idx["cards"]) == ["1"]
    mock.create_page = real  # type: ignore[method-assign,unused-ignore]
    stats, _ = _publish(mock, idx, wd)
    assert stats["created"] == 2 and len(mock.pages) == 3            # 첫 카드는 다시 만들지 않는다


def test_notion_plan_makes_no_calls(ready):
    mock, idx, wd = ready
    n = len(mock.calls)
    p = nt.plan(idx, wd)
    assert len(mock.calls) == n
    assert p["create"] == 3 and p["update_if_draft"] == 0 and p["markdown_chars"] > 0
    assert p["set_up"] is True


def test_notion_publish_needs_setup(tmp_path):
    site, priv = _src(tmp_path)
    wd = nt.load_week(site, priv, W)
    with pytest.raises(nt.NotionStageError):
        nt.publish_week(MockNotion(), nt.empty_index(), wd, save=lambda i: None, log=lambda m: None)


def test_notion_index_round_trip(tmp_path):
    p = tmp_path / "notion" / "index.json"
    assert nt.load_index(p) == nt.empty_index()
    idx = nt.empty_index()
    idx["weeks"][W] = {"page_id": "x", "url": "u"}
    nt.save_index(p, idx)
    assert nt.load_index(p) == idx
