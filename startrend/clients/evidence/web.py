"""웹 근거 — 검색은 우리 코드가 한다 (SPEC FR-5.3, 결정 46, MEASURE §15).

Tavily Search(`POST /search`, basic = 1크레딧, 무료 월 1,000크레딧)로 저장소마다 검색어 2~3개를 보내
결과 URL·제목·스니펫·발행일을 근거 목록에 남긴다. 저장소 자신의 GitHub 페이지는 GitHub 출처(FR-5.1)가
맡으므로 뺀다.
Reddit·X 결과도 남기되 본문은 읽지 않는다 — `extra["fetchable"]` 이 False 다(결정 52).
Claude 는 이 목록 안에서만 판정·요약한다 — 본문이 필요하면 web_fetch 로 읽는다(P3-4 뒷부분, 과금 단계).
키는 Authorization 헤더로만 보내고, 오류 메시지·repr 에 남기지 않는다(NFR-8).
"""

import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from startrend.clients.evidence.base import SourceError, Target
from startrend.clients.transport import Poster, TransportError
from startrend.core import evidence as ev

API = "https://api.tavily.com/search"
CREDITS = {"basic": 1, "fast": 1, "ultra-fast": 1, "advanced": 2}
MAX_RESULTS = 8
# 링크·스니펫은 남기되 본문(web_fetch)은 읽지 않는 곳 (결정 52)
# - Reddit: robots 로 전부 막혀 있다(부록 C-2). API 는 사전 승인제(결정 44)
# - X: API 는 유료(D-22)이고 약관이 본문 저장·재표시를 막는다 — 페이지를 긁지 않는다. t.co 는 X 의 단축 주소
NO_FETCH_HOSTS = ("reddit.com", "redd.it", "x.com", "twitter.com", "t.co")


def iso_date(raw: str) -> str | None:
    """발행일을 ISO 8601 로. Tavily 는 RFC 1123(`Mon, 19 Oct 2026 21:49:06 GMT`)으로 준다(2026-10-28 실호출).
    이미 ISO 면 그대로, 읽을 수 없으면 None — 다른 출처와 섞어 날짜순으로 줄 세우기 위함(FR-6.3)."""
    s = raw.strip()
    try:
        date.fromisoformat(s[:10])
        return s
    except ValueError:
        pass
    try:
        t = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=UTC)
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetchable(url: str) -> bool:
    """본문을 읽어도 되는 URL 인가. 정규화한 호스트가 NO_FETCH_HOSTS 이거나 그 하위 도메인이면 아니다."""
    key = ev.normalize_url(url)
    if key is None:
        return False
    host = key.split("/")[2].rsplit("@", 1)[-1].split(":")[0]
    return not any(host == h or host.endswith("." + h) for h in NO_FETCH_HOSTS)


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
                "include_answer": False, "include_raw_content": False,
                "include_published_date": True}            # 결정 52 — 급등일 타임라인 재료
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
                    published_at=iso_date(str(r["published_date"])) if r.get("published_date") else None,
                    extra={"score": r.get("score"), "query": q, "fetchable": fetchable(str(url))}))
        return ev.dedupe(docs)
