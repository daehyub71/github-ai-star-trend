"""core.evidence — 근거 문서마다 URL·가져온 시각·콘텐츠 해시를 남긴다 (FR-5.6). 인용 게이트의 기준이다."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from startrend.core import evidence as ev

T = datetime(2026, 10, 28, 5, 0, tzinfo=UTC)


# --- URL 정규화 ---


@pytest.mark.parametrize("raw, want", [
    ("HTTPS://WWW.Example.com:443/a/b/?utm_source=x&b=2&a=1#frag", "https://example.com/a/b?a=1&b=2"),
    ("http://example.com/", "https://example.com"),
    ("https://example.com:8080/x", "https://example.com:8080/x"),
    ("https://example.com/%7Euser", "https://example.com/~user"),
    ("https://github.com/Owner/Repo/blob/Main/README.md", "https://github.com/owner/repo/blob/Main/README.md"),
    ("https://news.ycombinator.com/item?id=123", "https://news.ycombinator.com/item?id=123"),
    ("  https://example.com/x  ", "https://example.com/x"),
    ("www.example.com/x", "https://example.com/x"),
])
def test_evidence_normalize_url_canonical_forms(raw, want):
    assert ev.normalize_url(raw) == want


@pytest.mark.parametrize("raw", [
    "javascript:alert(1)", "data:text/html;base64,AAAA", "mailto:a@b.c", "ftp://example.com/x",
    "/relative/path", "//example.com/x", "example.com/x", "", "https://", "https:///x",
])
def test_evidence_normalize_url_rejects_non_web_links(raw):
    assert ev.normalize_url(raw) is None


def test_evidence_normalize_url_keeps_userinfo_so_lookalikes_do_not_match():
    # "allowed.com@evil.com" 의 실제 호스트는 evil.com 이다 — 허용 URL 과 같아지면 안 된다
    assert ev.normalize_url("https://allowed.com@evil.com/x") != ev.normalize_url("https://allowed.com/x")


# --- 문서 만들기 ---


def test_evidence_make_records_url_time_and_content_hash():
    d = ev.make(url="https://news.ycombinator.com/item?id=1", source="hn", kind="story", title="Show HN: r",
                text="hello   world\n\nagain", fetched_at=T, published_at="2026-10-20T01:00:00Z",
                extra={"points": 120})
    assert d.fetched_at == "2026-10-28T05:00:00Z"
    assert d.content_hash == ev.text_hash("hello   world\n\nagain") and len(d.content_hash) == 16
    assert d.excerpt == "hello world again"
    assert d.key == "https://news.ycombinator.com/item?id=1"
    assert d.extra == {"points": 120}


def test_evidence_make_converts_time_to_utc_and_caps_excerpt():
    kst = timezone(timedelta(hours=9))
    d = ev.make(url="https://e.com/x", source="web", kind="search", title="t", text="가" * 1000,
                fetched_at=datetime(2026, 10, 28, 14, 0, tzinfo=kst))
    assert d.fetched_at == "2026-10-28T05:00:00Z"
    assert len(d.excerpt) <= ev.EXCERPT_CHARS


def test_evidence_make_rejects_naive_time_and_bad_url():
    with pytest.raises(ValueError):
        ev.make(url="https://e.com/x", source="web", kind="search", title="t", text="x",
                fetched_at=datetime(2026, 10, 28))
    with pytest.raises(ValueError):
        ev.make(url="javascript:alert(1)", source="web", kind="search", title="t", text="x", fetched_at=T)


def test_evidence_record_round_trip_leaves_full_text_out():
    d = ev.make(url="https://e.com/x", source="web", kind="search", title="t", text="본문 " * 400,
                fetched_at=T)
    rec = d.record()
    assert "text" not in rec and rec["content_hash"] == d.content_hash
    back = ev.from_record(rec)
    assert back.url == d.url and back.excerpt == d.excerpt and back.text == ""


@pytest.mark.parametrize("url, want", [
    ("https://github.com/Synth-Lab/Agent-Kit", "synth-lab/agent-kit"),
    ("https://github.com/o/r.git", "o/r"),
    ("http://www.github.com/o/r/tree/main/docs?x=1", "o/r"),
    ("git+https://github.com/o/r.git", "o/r"),
    ("https://github.com/o", None),
    ("https://gitlab.com/o/r", None),
    ("https://github.com.evil.example/o/r", None),
])
def test_evidence_github_repo_of_a_url(url, want):
    assert ev.github_repo(url) == want


def test_evidence_dedupe_keeps_first_by_normalized_url():
    a = ev.make(url="https://e.com/x/", source="web", kind="search", title="a", text="1", fetched_at=T)
    b = ev.make(url="http://www.e.com/x#top", source="hn", kind="comment", title="b", text="2", fetched_at=T)
    c = ev.make(url="https://e.com/y", source="web", kind="search", title="c", text="3", fetched_at=T)
    assert [d.title for d in ev.dedupe([a, b, c])] == ["a", "c"]
