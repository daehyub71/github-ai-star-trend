"""clients.evidence.hn — Algolia HN Search: 저장소 URL 이 걸린 글 + 이름이 나온 댓글 (FR-5.2, 결정 44).

전송을 주입해 네트워크 없이 검증한다. 마지막 live 테스트만 실제 API 를 부른다(`pytest -m live`, 키 없음).
"""

import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from startrend.clients.evidence.base import SourceError, Target
from startrend.clients.evidence.hn import HNSource
from startrend.clients.transport import HttpResponse, TransportError, UrllibTransport

NOW = datetime(2026, 10, 28, 5, 0, tzinfo=UTC)
TARGET = Target(1, "acme/graphify", since=date(2026, 10, 18), until=date(2026, 10, 24),
                focus=(date(2026, 10, 21),))


def _story(oid: str, day: int, points: int, title: str = "Show HN: Graphify") -> dict[str, Any]:
    return {"objectID": oid, "title": title, "url": "https://github.com/acme/graphify", "author": "u",
            "points": points, "num_comments": 3, "created_at": f"2026-10-{day:02d}T01:00:00.000Z",
            "created_at_i": int(datetime(2026, 10, day, 1, tzinfo=UTC).timestamp()), "story_text": None}


def _comment(oid: str, day: int, text: str) -> dict[str, Any]:
    return {"objectID": oid, "comment_text": text, "author": "c", "story_id": 9,
            "story_title": "Ask HN: tools", "created_at": f"2026-10-{day:02d}T02:00:00.000Z",
            "created_at_i": int(datetime(2026, 10, day, 2, tzinfo=UTC).timestamp())}


class FakeTransport:
    def __init__(self, by_tag: Mapping[str, HttpResponse | Exception]):
        self.by_tag = dict(by_tag)
        self.urls: list[str] = []

    def __call__(self, method: str, url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
        self.urls.append(url)
        r = self.by_tag[parse_qs(urlsplit(url).query)["tags"][0]]
        if isinstance(r, Exception):
            raise r
        return r


def ok(hits: list[dict[str, Any]]) -> HttpResponse:
    return HttpResponse(200, {}, json.dumps({"hits": hits, "nbHits": len(hits)}).encode())


def _src(stories: list[dict[str, Any]], comments: list[dict[str, Any]],
         **kw) -> tuple[HNSource, FakeTransport]:
    t = FakeTransport({"story": ok(stories), "comment": ok(comments)})
    return HNSource(t, clock=lambda: NOW, **kw), t


def test_hn_queries_story_urls_and_comment_names_inside_the_window():
    src, t = _src([], [])
    src.collect(TARGET)
    story, comment = (parse_qs(urlsplit(u).query) for u in t.urls)
    assert all(urlsplit(u).netloc == "hn.algolia.com" and "/search_by_date" in u for u in t.urls)
    assert story["query"] == ["github.com/acme/graphify"] and story["restrictSearchableAttributes"] == ["url"]
    t0 = int(datetime(2026, 10, 18, tzinfo=UTC).timestamp())
    t1 = int(datetime(2026, 10, 25, tzinfo=UTC).timestamp())
    assert story["numericFilters"] == [f"created_at_i>={t0},created_at_i<{t1}"]
    assert comment["query"] == ["graphify"] and comment["tags"] == ["comment"]


def test_hn_turns_hits_into_evidence_with_item_urls():
    src, _ = _src([_story("101", 21, 250)],
                  [_comment("202", 22, "<p>Tried <a href=\"https://github.com/acme/graphify\">graphify</a>"
                                       " &amp; it works</p>")])
    story, comment = src.collect(TARGET)
    assert story.url == "https://news.ycombinator.com/item?id=101" and story.kind == "story"
    assert story.source == "hn" and story.title == "Show HN: Graphify"
    assert story.extra == {"points": 250, "comments": 3, "author": "u", "linked_url": "https://github.com/acme/graphify"}
    assert story.published_at == "2026-10-21T01:00:00.000Z" and story.fetched_at == "2026-10-28T05:00:00Z"
    assert comment.url == "https://news.ycombinator.com/item?id=202" and comment.kind == "comment"
    assert comment.text == "Tried graphify & it works" and comment.extra["story_id"] == 9


def test_hn_keeps_only_comments_that_name_the_repo_as_a_word():
    src, _ = _src([], [_comment("1", 22, "graphify is neat"), _comment("2", 22, "graphifying data"),
                       _comment("3", 22, "see acme/graphify"), _comment("4", 22, "GRAPHIFY!")])
    assert [d.url[-1] for d in src.collect(TARGET)] == ["1", "3", "4"]


def test_hn_prefers_hits_near_the_spike_day_and_caps_counts():
    stories = [_story("a", 18, 900), _story("b", 21, 5), _story("c", 22, 50), _story("d", 24, 1000)]
    src, _ = _src(stories, [], max_stories=2)
    # 급등일(21일)에서 가까운 순 → 같으면 점수 큰 순
    assert [d.url.rsplit("=", 1)[1] for d in src.collect(TARGET)] == ["b", "c"]


def test_hn_without_focus_orders_by_points():
    stories = [_story("a", 18, 9), _story("b", 21, 500)]
    src, _ = _src(stories, [])
    t = Target(1, "acme/graphify", since=date(2026, 10, 18), until=date(2026, 10, 24))
    assert [d.url[-1] for d in src.collect(t)] == ["b", "a"]


@pytest.mark.parametrize("resp", [
    HttpResponse(503, {}, b"busy"),
    HttpResponse(200, {}, b"<html>not json"),
    HttpResponse(200, {}, b'{"nohits": []}'),
    TransportError("GET https://hn.algolia.com/api/v1/search_by_date: timed out"),
])
def test_hn_failures_become_source_errors(resp):
    t = FakeTransport({"story": resp, "comment": ok([])})
    with pytest.raises(SourceError):
        HNSource(t, clock=lambda: NOW).collect(TARGET)


def test_hn_skips_malformed_hits_instead_of_failing():
    src, _ = _src([{"objectID": "1"}, _story("2", 21, 10)], [{"comment_text": None, "objectID": "3"}])
    assert [d.url[-1] for d in src.collect(TARGET)] == ["2"]


@pytest.mark.live
def test_hn_live_returns_items_for_a_known_repo():
    now = datetime.now(UTC)
    t = Target(1, "ollama/ollama", since=date(2026, 1, 1), until=now.date())
    docs = HNSource(UrllibTransport(), clock=lambda: now).collect(t)
    assert docs and all(d.url.startswith("https://news.ycombinator.com/item?id=") for d in docs)
