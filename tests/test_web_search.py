"""clients.evidence.web — 웹 검색은 우리 코드가 한다(FR-5.3, 결정 46). Tavily basic, 저장소마다 검색어 2~3개.

결과 URL·제목·스니펫을 근거 목록에 남긴다. Claude 는 그 목록 안에서만 판정·요약한다(P3-4 뒷부분).
전송을 주입해 네트워크 없이 검증한다. live 테스트만 실제로 부른다(`pytest -m live`, 무료 크레딧 1개).
"""

import json
import os
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any

import pytest

from startrend.clients.evidence.base import SourceError, Target
from startrend.clients.evidence.web import TavilySource, default_queries
from startrend.clients.transport import HttpResponse, TransportError, UrllibPoster

KEY = "tvly-test-key-value"
NOW = datetime(2026, 10, 28, 5, 0, tzinfo=UTC)
TARGET = Target(1, "Graphify-Labs/graphify", since=date(2026, 10, 18), until=date(2026, 10, 24))


class FakePoster:
    def __init__(self, responses: list[HttpResponse | Exception]):
        self.responses = list(responses)
        self.sent: list[tuple[str, dict[str, str], dict[str, Any]]] = []

    def __call__(self, url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> HttpResponse:
        self.sent.append((url, dict(headers), json.loads(body)))
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r


def ok(results: list[dict[str, Any]]) -> HttpResponse:
    body = {"query": "q", "results": results, "response_time": 1.2}
    return HttpResponse(200, {}, json.dumps(body).encode())


def _r(url: str, title: str = "t", content: str = "snippet", **kw) -> dict[str, Any]:
    return {"url": url, "title": title, "content": content, "score": 0.8, **kw}


def test_web_default_queries_are_two_to_three():
    qs = default_queries(TARGET)
    assert 2 <= len(qs) <= 3 and qs[0] == "Graphify-Labs/graphify"
    assert all("graphify" in q.lower() for q in qs)


def test_web_sends_basic_search_with_bearer_key():
    p = FakePoster([ok([])])
    TavilySource(p, KEY, clock=lambda: NOW).collect(TARGET)
    url, headers, body = p.sent[0]
    assert url == "https://api.tavily.com/search"
    assert headers["Authorization"] == f"Bearer {KEY}" and headers["Content-Type"] == "application/json"
    assert body["query"] == "Graphify-Labs/graphify" and body["search_depth"] == "basic"
    assert body["include_answer"] is False and body["include_raw_content"] is False
    assert 1 <= body["max_results"] <= 20 and KEY not in json.dumps(body)


def test_web_results_become_evidence_without_the_repo_itself():
    p = FakePoster([
        ok([_r("https://dev.to/a/graphify-review", "Graphify review", "I tried it",
               published_date="2026-10-20"),
            _r("https://github.com/Graphify-Labs/graphify", "repo"),
            _r("https://github.com/graphify-labs/graphify/issues/3", "issue")]),
        ok([_r("https://dev.to/a/graphify-review/", "dup"), _r("https://blog.example.com/t", "Tutorial")]),
        ok([]),
    ])
    src = TavilySource(p, KEY, clock=lambda: NOW)
    docs = src.collect(TARGET)
    assert [d.url for d in docs] == ["https://dev.to/a/graphify-review", "https://blog.example.com/t"]
    d = docs[0]
    assert (d.source, d.kind, d.title, d.text) == ("web", "search", "Graphify review", "I tried it")
    assert d.published_at == "2026-10-20" and d.extra == {"score": 0.8, "query": "Graphify-Labs/graphify"}
    assert src.credits == 3 and len(p.sent) == 3


def test_web_skips_results_without_a_web_url():
    p = FakePoster([ok([_r("javascript:alert(1)"), {"title": "no url"}, _r("https://e.com/x")])])
    docs = TavilySource(p, KEY, clock=lambda: NOW, queries=lambda t: ["q"]).collect(TARGET)
    assert [d.url for d in docs] == ["https://e.com/x"]


@pytest.mark.parametrize("resp", [
    HttpResponse(401, {}, b'{"detail": {"error": "Unauthorized"}}'),
    HttpResponse(432, {}, b"{}"),
    HttpResponse(429, {}, b"{}"),
    HttpResponse(200, {}, b"not json"),
    HttpResponse(200, {}, b'{"results": "x"}'),
    TransportError("POST https://api.tavily.com/search: timed out"),
])
def test_web_failures_become_source_errors_without_the_key(resp):
    with pytest.raises(SourceError) as e:
        TavilySource(FakePoster([resp]), KEY, clock=lambda: NOW).collect(TARGET)
    assert KEY not in str(e.value)


def test_web_repr_hides_the_key():
    src = TavilySource(FakePoster([ok([])]), KEY, clock=lambda: NOW)
    assert KEY not in repr(src) and KEY not in str(src)


def test_web_requires_a_key():
    with pytest.raises(ValueError):
        TavilySource(FakePoster([ok([])]), "", clock=lambda: NOW)


@pytest.mark.live
def test_web_live_one_search():
    key = os.environ.get("STARTREND_TAVILY_API_KEY", "")
    if not key:
        pytest.skip("STARTREND_TAVILY_API_KEY 없음")
    src = TavilySource(UrllibPoster(), key, queries=lambda t: [t.full_name])   # 크레딧 1개
    docs = src.collect(TARGET)
    assert src.credits == 1 and all(d.url.startswith("http") for d in docs)
