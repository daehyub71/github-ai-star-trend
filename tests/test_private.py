"""stages.private — 비공개 저장소 ↔ 작업 폴더 동기화 (FR-11.8, 결정 55). 파일 복사만 — git 은 워크플로가 한다.

비공개 저장소 배치: cards/(최신 카드 보관소) · weeks/<주>/briefing.md · weeks/<주>/cards/ · site-private/
                   · notion/index.json · weeks/<주>/blog/(만든 그림 gen/ 제외 — 결정 66)
작업 폴더 배치:     .work/cards/ · .work/<주>/briefing.md · .work/<주>/cards/ · .work/site-private/
                   · .work/notion/index.json · .work/<주>/blog/
근거 원문·캐시·스냅샷은 옮기지 않는다(원문은 압축본으로, 스냅샷은 공개 Release 로).
"""

import json
from pathlib import Path
from typing import Any

from startrend.stages import private


def _put(p: Path, text: str = "x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def test_private_push_copies_cards_briefings_and_site_copy_only(tmp_path):
    work, priv = tmp_path / "w", tmp_path / "p"
    _put(work / "cards" / "1.md")
    _put(work / "cards" / "1.json")
    _put(work / "2026-10-25" / "briefing.md")
    _put(work / "2026-10-25" / "cards" / "o__a.md")
    _put(work / "2026-10-25" / "raw" / "abc.txt")             # 원문 — 옮기지 않는다
    _put(work / "2026-10-25" / "evidence.jsonl")              # 근거 목록 — 압축본으로만
    _put(work / "site-private" / "cards" / "o__a.md")
    _put(work / "cache" / "x.json")
    _put(work / "snapshots" / "2026-10-25.csv")
    stats = private.push(work, priv)
    assert _files(priv) == ["cards/1.json", "cards/1.md", "site-private/cards/o__a.md",
                            "weeks/2026-10-25/briefing.md", "weeks/2026-10-25/cards/o__a.md"]
    assert stats["files"] == 5


def test_private_pull_restores_the_work_layout(tmp_path):
    work, priv = tmp_path / "w", tmp_path / "p"
    _put(priv / "cards" / "1.md", "카드")
    _put(priv / "weeks" / "2026-10-18" / "briefing.md", "브리핑")
    _put(priv / "weeks" / "2026-10-18" / "cards" / "o__a.md")
    _put(priv / "site-private" / "briefings" / "2026-10-18.md")
    _put(priv / "README.md")                                    # 비공개 저장소의 다른 파일은 건드리지 않는다
    private.pull(priv, work)
    assert _files(work) == ["2026-10-18/briefing.md", "2026-10-18/cards/o__a.md", "cards/1.md",
                            "site-private/briefings/2026-10-18.md"]
    assert (work / "cards" / "1.md").read_text(encoding="utf-8") == "카드"


def test_private_sync_overwrites_but_never_deletes(tmp_path):
    # 사용자 데이터 원칙 — 한쪽에만 있는 파일을 지우지 않는다. 같은 파일은 새 내용으로 덮는다
    work, priv = tmp_path / "w", tmp_path / "p"
    _put(priv / "cards" / "old.md", "남는다")
    _put(priv / "cards" / "1.md", "옛 카드")
    _put(work / "cards" / "1.md", "새 카드")
    private.push(work, priv)
    assert (priv / "cards" / "old.md").read_text(encoding="utf-8") == "남는다"
    assert (priv / "cards" / "1.md").read_text(encoding="utf-8") == "새 카드"


def test_private_round_trip_keeps_bytes(tmp_path):
    work, priv, back = tmp_path / "w", tmp_path / "p", tmp_path / "w2"
    _put(work / "cards" / "1.md", "---\nrepo: o/a\n---\n# 한글 카드\r\n")
    private.push(work, priv)
    private.pull(priv, back)
    assert (back / "cards" / "1.md").read_bytes() == (work / "cards" / "1.md").read_bytes()


# --- 결정 66 — Notion 대응표 · 블로그 초안도 비공개 저장소에 (자동 실행과 로컬이 함께 쓴다) ---

def _index(path: Path, **parts: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"parent_page_id": "p", "databases": {}, "weeks": {}, "cards": {}, "blog": {},
                                **parts}, ensure_ascii=False), encoding="utf-8")
    return path


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_private_push_carries_the_notion_index_and_blog_drafts_without_made_pictures(tmp_path):
    work, priv = tmp_path / "w", tmp_path / "p"
    _index(work / "notion" / "index.json", weeks={"2026-10-25": {"page_id": "w1"}})
    blog = work / "2026-10-25" / "blog"
    for name in ("post.md", "draft.json", "images.md", "meta.json", "gate.json", "img/o__a.png"):
        _put(blog / name)
    _put(blog / "gen" / "1.png")                    # 사용자가 만든 그림 — 1주 37MB, 옮기지 않는다
    _put(blog / "gen" / "원본 그림.png")
    stats = private.push(work, priv)
    assert _files(priv) == ["notion/index.json"] + [
        f"weeks/2026-10-25/blog/{n}"
        for n in ("draft.json", "gate.json", "images.md", "img/o__a.png", "meta.json", "post.md")]
    assert stats["files"] == 7 and stats["conflicts"] == []


def test_private_index_merge_keeps_records_from_both_sides(tmp_path):
    # 대응표가 갈라지면 Notion 페이지가 중복으로 생긴다 — 한쪽에만 있는 기록을 잃지 않는다
    work, priv = tmp_path / "w", tmp_path / "p"
    _index(priv / "notion" / "index.json", weeks={"2026-11-01": {"page_id": "w2"}},
           cards={"1": {"page_id": "c1"}}, uploads={"h1": "u1"})
    _index(work / "notion" / "index.json", weeks={"2026-10-25": {"page_id": "w1"}},
           cards={"2": {"page_id": "c2"}}, uploads={"h2": "u2"}, databases={"blog": {"id": "db"}})
    stats = private.pull(priv, work)
    got = _read(work / "notion" / "index.json")
    assert set(got["weeks"]) == {"2026-10-25", "2026-11-01"} and set(got["cards"]) == {"1", "2"}
    assert got["uploads"] == {"h1": "u1", "h2": "u2"} and got["databases"] == {"blog": {"id": "db"}}
    assert stats["conflicts"] == []
    stats = private.push(work, priv)
    assert _read(priv / "notion" / "index.json") == got and stats["conflicts"] == []


def test_private_index_merge_keeps_the_receiving_side_on_a_conflict(tmp_path):
    work, priv = tmp_path / "w", tmp_path / "p"
    _index(priv / "notion" / "index.json", cards={"1": {"page_id": "theirs"}})
    _index(work / "notion" / "index.json", cards={"1": {"page_id": "mine"}})
    stats = private.pull(priv, work)
    assert _read(work / "notion" / "index.json")["cards"]["1"] == {"page_id": "mine"}
    assert stats["conflicts"] == ["notion/index.json: cards.1"]
    stats = private.push(work, priv)
    assert _read(priv / "notion" / "index.json")["cards"]["1"] == {"page_id": "theirs"}
    assert stats["conflicts"] == ["notion/index.json: cards.1"]


def test_private_pull_brings_only_blog_files_missing_locally(tmp_path):
    # 블로그 파일은 사람이 로컬에서 고친다(그림 결합 · 다시 그리기)
    # — 받을 때는 덮지 않고 알리고, 올릴 때는 덮는다
    work, priv = tmp_path / "w", tmp_path / "p"
    edited = "그림을 넣어 다시 그린 글"
    _put(priv / "weeks" / "2026-11-01" / "blog" / "post.md", "자동 실행 초안")
    _put(priv / "weeks" / "2026-11-01" / "blog" / "draft.json", "{}")
    _put(priv / "weeks" / "2026-11-01" / "blog" / "meta.json", "같음")
    _put(work / "2026-11-01" / "blog" / "post.md", edited)
    _put(work / "2026-11-01" / "blog" / "meta.json", "같음")
    stats = private.pull(priv, work)
    assert (work / "2026-11-01" / "blog" / "post.md").read_text(encoding="utf-8") == edited
    assert (work / "2026-11-01" / "blog" / "draft.json").exists()
    assert stats["kept_local"] == ["2026-11-01/blog/post.md"]
    private.push(work, priv)
    assert (priv / "weeks" / "2026-11-01" / "blog" / "post.md").read_text(encoding="utf-8") == edited


def test_private_push_from_actions_keeps_blog_files_already_in_the_private_repo(tmp_path):
    # 자동 실행의 작업 폴더에는 실행 시작 때 받은 예전 블로그 파일이 있다
    # — 그사이 로컬에서 고쳐 올린 것을 덮지 않는다
    work, priv = tmp_path / "w", tmp_path / "p"
    _put(priv / "weeks" / "2026-10-25" / "blog" / "post.md", "로컬에서 고쳐 올린 글")
    _put(work / "2026-10-25" / "blog" / "post.md", "실행 시작 때 받은 글")
    _put(work / "2026-11-01" / "blog" / "post.md", "이번 주 새 초안")
    stats = private.push(work, priv, keep_blog=True)
    blog = priv / "weeks"
    assert (blog / "2026-10-25" / "blog" / "post.md").read_text(encoding="utf-8") == "로컬에서 고쳐 올린 글"
    assert (blog / "2026-11-01" / "blog" / "post.md").read_text(encoding="utf-8") == "이번 주 새 초안"
    assert stats["kept_private"] == ["2026-10-25/blog/post.md"]
