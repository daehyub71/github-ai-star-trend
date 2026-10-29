"""stages.private — 비공개 저장소 ↔ 작업 폴더 동기화 (FR-11.8, 결정 55). 파일 복사만 — git 은 워크플로가 한다.

비공개 저장소 배치: cards/(최신 카드 보관소) · weeks/<주>/briefing.md · weeks/<주>/cards/ · site-private/
작업 폴더 배치:     .work/cards/ · .work/<주>/briefing.md · .work/<주>/cards/ · .work/site-private/
근거 원문·캐시·스냅샷은 옮기지 않는다(원문은 압축본으로, 스냅샷은 공개 Release 로).
"""

from pathlib import Path

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
