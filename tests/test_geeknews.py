"""clients.evidence.geeknews — GeekNews `/past?day=` 날짜별 목록에서 github.com 링크를 찾는다
(FR-5.5, 결정 44).

공식 API 가 없다. 근거 창 7일 × 몇 쪽(주 15~25회)만 읽고, 식별 가능한 User-Agent 와 요청 사이 간격을 둔다
(약관의 "과도한 부하" 금지). 한 주를 한 번 훑어 저장소별로 나눠 두고 대상마다 꺼낸다. 픽스처는 합성 HTML 이다.
"""

from collections.abc import Mapping
from datetime import UTC, date, datetime
from urllib.parse import parse_qs, urlsplit

import pytest

from startrend.clients.evidence.base import SourceError, Target
from startrend.clients.evidence.geeknews import GeekNewsSource, parse_past
from startrend.clients.transport import HttpResponse, TransportError
from tests import synth

NOW = datetime(2026, 10, 28, 5, 0, tzinfo=UTC)
PAGE = (synth.FIXTURES / "evidence" / "geeknews_past.html").read_text(encoding="utf-8")
EMPTY = "<html><body><div class='topics'></div></body></html>"
TARGET = Target(1, "synth-lab/agent-kit", since=date(2026, 10, 18), until=date(2026, 10, 24))


class FakeTransport:
    """2026-10-20 1쪽만 픽스처, 나머지는 빈 쪽."""

    def __init__(self, pages: Mapping[tuple[str, int], HttpResponse | Exception] | None = None):
        self.pages = dict(pages or {("2026-10-20", 1): HttpResponse(200, {}, PAGE.encode())})
        self.requests: list[tuple[str, dict[str, str]]] = []

    def __call__(self, method: str, url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
        self.requests.append((url, dict(headers)))
        q = parse_qs(urlsplit(url).query)
        key = (q["day"][0], int(q.get("page", ["1"])[0]))
        r = self.pages.get(key, HttpResponse(200, {}, EMPTY.encode()))
        if isinstance(r, Exception):
            raise r
        return r


def _src(t: FakeTransport, **kw) -> tuple[GeekNewsSource, list[float]]:
    slept: list[float] = []
    return GeekNewsSource(t, clock=lambda: NOW, sleep=slept.append, **kw), slept


def test_geeknews_parse_past_reads_topics():
    topics, has_next = parse_past(PAGE, "2026-10-20", 1)
    assert has_next is True and [t.topic_id for t in topics] == [9001, 9002, 9003]
    t = topics[0]
    assert t.link == "https://github.com/Synth-Lab/Agent-Kit"
    assert t.title == "Agent Kit - 합성 에이전트 도구 & 예제"
    assert t.desc == "합성 픽스처용 설명입니다. 에이전트를 <빠르게> 만든다..."
    assert (t.points, t.comments, t.published_at) == (38, 3, "2026-10-20T09:30:02+09:00")
    assert parse_past(EMPTY, "2026-10-20", 1) == ([], False)


def test_geeknews_parse_past_detects_a_layout_change():
    # 글 블록은 있는데 아무것도 읽지 못하면 형식이 바뀐 것이다 — 조용히 0건으로 넘기지 않는다
    broken = "<div class='topic_row' data-topic-state-id='1'><div class=topictitle>바뀐 모양</div></div>"
    with pytest.raises(SourceError):
        parse_past(broken, "2026-10-20", 1)


def test_geeknews_collects_topics_linking_the_repo_or_its_subpaths():
    src, _ = _src(FakeTransport())
    docs = src.collect(TARGET)
    assert [d.url for d in docs] == ["https://news.hada.io/topic?id=9001", "https://news.hada.io/topic?id=9003"]
    d = docs[0]
    assert d.source == "geeknews" and d.kind == "story" and d.title == "Agent Kit - 합성 에이전트 도구 & 예제"
    assert d.published_at == "2026-10-20T00:30:02Z"
    assert d.extra == {"points": 38, "comments": 3, "linked_url": "https://github.com/Synth-Lab/Agent-Kit"}


def test_geeknews_scans_each_day_once_with_pages_and_a_polite_delay():
    t = FakeTransport()
    src, slept = _src(t, delay=2.0)
    src.collect(TARGET)
    days = [parse_qs(urlsplit(u).query)["day"][0] for u, _ in t.requests]
    assert days == ["2026-10-18", "2026-10-19", "2026-10-20", "2026-10-20", "2026-10-21", "2026-10-22",
                    "2026-10-23", "2026-10-24"]          # 20일은 다음 쪽이 있다
    assert len(slept) == len(t.requests) - 1 and set(slept) == {2.0}
    ua = t.requests[0][1]["User-Agent"]
    assert ua.startswith("startrend/") and "github.com/" in ua
    # 다른 저장소는 이미 훑은 주에서 꺼낸다 — 다시 부르지 않는다
    assert src.collect(Target(2, "other/repo", since=TARGET.since, until=TARGET.until)) == []
    assert len(t.requests) == 8


def test_geeknews_stops_at_max_pages():
    page = PAGE  # 매 쪽 "다음 쪽"이 있다
    pages = {("2026-10-20", n): HttpResponse(200, {}, page.replace("page=2", f"page={n + 1}").encode())
             for n in range(1, 10)}
    t = FakeTransport(pages)
    src, _ = _src(t, max_pages=3)
    src.collect(TARGET)
    assert sum(1 for u, _ in t.requests if "day=2026-10-20" in u) == 3


@pytest.mark.parametrize("bad", [HttpResponse(503, {}, b"busy"),
                                 TransportError("GET https://news.hada.io: timeout")])
def test_geeknews_failures_become_source_errors(bad):
    t = FakeTransport({("2026-10-18", 1): bad})
    with pytest.raises(SourceError):
        _src(t)[0].collect(TARGET)


def test_geeknews_remembers_a_failed_week_instead_of_rescanning_per_repo():
    # 한 주 훑기가 실패하면 대상 저장소마다 다시 훑지 않는다 — 사이트에 부하를 주지 않기 위함(약관)
    t = FakeTransport({("2026-10-19", 1): HttpResponse(503, {}, b"busy")})
    src, _ = _src(t)
    for name in ("synth-lab/agent-kit", "other/repo", "third/repo"):
        with pytest.raises(SourceError):
            src.collect(Target(1, name, since=TARGET.since, until=TARGET.until))
    assert len(t.requests) == 2
