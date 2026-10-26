"""core.hashing — 콘텐츠 해시가 정체성·증분의 기준이다 (워크스페이스 원칙 5)."""

from startrend.core import hashing


def test_hashing_sha256_text_known_value():
    assert hashing.sha256_text("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_hashing_content_hash_ignores_key_order():
    assert hashing.content_hash({"a": 1, "b": [1, 2]}) == hashing.content_hash({"b": [1, 2], "a": 1})


def test_hashing_content_hash_detects_change():
    assert hashing.content_hash({"a": 1}) != hashing.content_hash({"a": 2})


def test_hashing_short_hash_length():
    assert len(hashing.short_hash("x")) == 12
