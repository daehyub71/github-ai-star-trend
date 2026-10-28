"""core.meta — 랭킹에 든 저장소의 천천히 바뀌는 정보. 정체성은 숫자 ID (PLAN 1-5, NFR-5 ①·④)."""

from startrend.core import meta


def test_meta_shard_is_two_hex_chars_and_stable():
    s = meta.shard(900001)
    assert len(s) == 2 and all(c in "0123456789abcdef" for c in s)
    assert meta.shard(900001) == s


def test_meta_save_and_load(tmp_path):
    m = {"id": 7, "full_name": "a/b", "description": "x"}
    assert meta.save(tmp_path, m) is True
    assert meta.load(tmp_path, 7) == m
    path = meta.meta_path(tmp_path, 7, "a/b")
    assert path.parent.name == "a__b" and path.parent.parent.name == meta.shard(7)


def test_meta_save_unchanged_is_noop(tmp_path):
    m = {"id": 7, "full_name": "a/b"}
    meta.save(tmp_path, m)
    assert meta.save(tmp_path, dict(m)) is False


def test_meta_rename_moves_folder_and_keeps_alias(tmp_path):
    meta.save(tmp_path, {"id": 7, "full_name": "old/name", "aliases": []})
    meta.save(tmp_path, {"id": 7, "full_name": "new/name"})
    assert not meta.meta_path(tmp_path, 7, "old/name").exists()
    m = meta.load(tmp_path, 7)
    assert m is not None
    assert m["full_name"] == "new/name" and m["aliases"] == ["old/name"]


def test_meta_card_moves_with_rename(tmp_path):
    meta.save(tmp_path, {"id": 7, "full_name": "old/name"})
    card = meta.meta_path(tmp_path, 7, "old/name").parent / "card.md"
    card.write_text("# card", encoding="utf-8")
    meta.save(tmp_path, {"id": 7, "full_name": "new/name"})
    moved = meta.meta_path(tmp_path, 7, "new/name").parent / "card.md"
    assert moved.read_text(encoding="utf-8") == "# card"


def test_meta_load_missing_is_none(tmp_path):
    assert meta.load(tmp_path, 123) is None


def test_meta_classified_index_reads_every_meta_once(tmp_path):
    # 판정 결과 색인 — 주마다 수만 건을 하나씩 찾지 않게 한 번 훑는다 (P2-6·P2-7)
    meta.save(tmp_path, {"id": 7, "full_name": "a/b", "classify": {"status": "ok", "is_ai": True}})
    meta.save(tmp_path, {"id": 8, "full_name": "c/d"})                     # 판정 전
    meta.save(tmp_path, {"id": 9, "full_name": "e/f", "classify": {"status": "refused"}})
    idx = meta.classified(tmp_path)
    assert idx == {7: {"status": "ok", "is_ai": True}, 9: {"status": "refused"}}
    assert meta.classified(tmp_path / "nowhere") == {}
