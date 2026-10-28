"""웹 근거 — 검색은 우리 코드가 한다 (SPEC FR-5.3, 결정 46, MEASURE §15).

Tavily Search(`POST /search`, basic = 1크레딧, 무료 월 1,000크레딧)로 저장소마다 검색어 2~3개를 보내
결과 URL·제목·스니펫을 근거 목록에 남긴다. 저장소 자신의 GitHub 페이지는 GitHub 출처(FR-5.1)가 맡으므로 뺀다.
Claude 는 이 목록 안에서만 판정·요약한다 — 본문이 필요하면 web_fetch 로 읽는다(P3-4 뒷부분, 과금 단계).
키는 Authorization 헤더로만 보내고, 오류 메시지·repr 에 남기지 않는다(NFR-8).
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from startrend.clients.evidence.base import SourceError, Target
from startrend.clients.transport import Poster, TransportError
from startrend.core import evidence as ev

API = "https://api.tavily.com/search"
CREDITS = {"basic": 1, "fast": 1, "ultra-fast": 1, "advanced": 2}
MAX_RESULTS = 8


def default_queries(t: Target) -> list[str]:
    """블로그·튜토리얼·사용 후기를 찾는 검색어 3개 (FR-5.3). 첫째는 저장소 이름 그대로."""
    return [t.full_name, f"{t.name} github tutorial", f"{t.name} review"]


class TavilySource:
    def __init__(self, poster: Poster, api_key: str, *,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 queries: Callable[[Target], list[str]] = default_queries, depth: str = "basic",
                 max_results: int = MAX_RESULTS, timeout: float = 30.0):
        if not api_key:
            raise ValueError("Tavily 키가 없다 — STARTREND_TAVILY_API_KEY")
        if depth not in CREDITS:
            raise ValueError(f"search_depth 를 알 수 없다: {depth}")
        self._post = poster
        self._key = api_key
        self._clock = clock
        self._queries = queries
        self.depth = depth
        self.max_results = max_results
        self.timeout = timeout
        self.credits = 0

    def __repr__(self) -> str:
        return f"TavilySource(depth={self.depth!r}, max_results={self.max_results}, credits={self.credits})"

    @property
    def name(self) -> str:
        return "web"

    def _search(self, query: str) -> list[dict[str, Any]]:
        body = {"query": query, "search_depth": self.depth, "max_results": self.max_results,
                "include_answer": False, "include_raw_content": False}
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json",
                   "Accept": "application/json"}
        try:
            resp = self._post(API, headers, json.dumps(body).encode("utf-8"), self.timeout)
        except TransportError as e:
            raise SourceError(f"Tavily 연결 실패: {e}") from e
        self.credits += CREDITS[self.depth]       # 실패한 요청도 크레딧을 쓸 수 있다 — 크게 센다
        if resp.status != 200:
            raise SourceError(f"Tavily {resp.status}")
        try:
            results = json.loads(resp.body)["results"]
        except (ValueError, KeyError, TypeError) as e:
            raise SourceError(f"Tavily 응답 형식이 다르다: {type(e).__name__}") from e
        if not isinstance(results, list):
            raise SourceError("Tavily 응답 형식이 다르다: results 가 목록이 아니다")
        return [r for r in results if isinstance(r, dict)]

    def collect(self, target: Target) -> list[ev.Evidence]:
        now = self._clock()
        own = ev.normalize_url(f"https://github.com/{target.full_name}") or ""
        docs: list[ev.Evidence] = []
        for q in self._queries(target):
            for r in self._search(q):
                url = r.get("url")
                key = ev.normalize_url(url) if isinstance(url, str) else None
                if key is None or key == own or key.startswith(own + "/"):
                    continue
                docs.append(ev.make(
                    url=str(url), source="web", kind="search", title=str(r.get("title") or ""),
                    text=str(r.get("content") or ""), fetched_at=now,
                    published_at=str(r["published_date"]) if r.get("published_date") else None,
                    extra={"score": r.get("score"), "query": q}))
        return ev.dedupe(docs)
