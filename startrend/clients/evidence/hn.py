"""HN 근거 — Algolia HN Search (SPEC FR-5.2, 결정 44, 부록 C-2). 인증 없음·무료.

저장소마다 두 번 부른다: 저장소 URL 이 걸린 글(tags=story, url 에서만 찾기)과 이름이 나온 댓글
(tags=comment). 창은 Target 의 since~until(UTC 날짜). 급등일(focus)이 있으면 그 날에 가까운 것부터,
없으면 점수 순으로 자른다. 댓글은 이름이 단어로 들어 있는 것만 남긴다(Algolia 는 오타·접두어도 맞춘다).
근거 URL 은 HN 토론 페이지(item?id=)다 — 글이 가리키는 곳은 대개 저장소 자신이라서.
"""

import html
import json
import re
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from urllib.parse import urlencode

from startrend.clients.evidence.base import SourceError, Target
from startrend.clients.transport import Transport, TransportError
from startrend.core import evidence as ev

API = "https://hn.algolia.com/api/v1/search_by_date"
ITEM = "https://news.ycombinator.com/item?id="
HITS_PER_PAGE = 50
USER_AGENT = "startrend/0.0.1"

_Hit = tuple[dict[str, Any], ev.Evidence]     # (원래 hit, 만든 근거) — 정렬에 hit 의 시각·점수를 쓴다


def _epoch(d: date) -> int:
    return int(datetime.combine(d, time(), tzinfo=UTC).timestamp())


def strip_html(s: str) -> str:
    s = re.sub(r"(?i)<p\s*/?>", "\n\n", s)
    s = re.sub(r"<[^>]*>", "", s)
    return html.unescape(s).strip()


class HNSource:
    def __init__(self, transport: Transport, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 timeout: float = 20.0, max_stories: int = 10, max_comments: int = 20):
        self._t = transport
        self._clock = clock
        self._timeout = timeout
        self.max_stories = max_stories
        self.max_comments = max_comments
        self.calls = 0

    @property
    def name(self) -> str:
        return "hn"

    def _search(self, target: Target, *, query: str, tags: str, url_only: bool) -> list[dict[str, Any]]:
        params = {"query": query, "tags": tags, "hitsPerPage": str(HITS_PER_PAGE),
                  "numericFilters": f"created_at_i>={_epoch(target.since)},"
                                    f"created_at_i<{_epoch(target.until + timedelta(days=1))}"}
        if url_only:
            params["restrictSearchableAttributes"] = "url"
        url = f"{API}?{urlencode(params)}"
        self.calls += 1
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        try:
            resp = self._t("GET", url, headers, self._timeout)
        except TransportError as e:
            raise SourceError(f"HN 연결 실패: {e}") from e
        if resp.status != 200:
            raise SourceError(f"HN {resp.status} ({tags})")
        try:
            hits = json.loads(resp.body)["hits"]
        except (ValueError, KeyError, TypeError) as e:
            raise SourceError(f"HN 응답 형식이 다르다 ({tags}): {e}") from e
        if not isinstance(hits, list):
            raise SourceError(f"HN 응답 형식이 다르다 ({tags}): hits 가 목록이 아니다")
        return [h for h in hits if isinstance(h, dict)]

    def _order(self, target: Target, hits: list[_Hit], cap: int) -> list[ev.Evidence]:
        """급등일에서 가까운 순 → 점수 큰 순 → 받은 순."""
        def key(pair: tuple[int, _Hit]) -> tuple[int, int, int]:
            i, (h, _) = pair
            day = datetime.fromtimestamp(int(h["created_at_i"]), tz=UTC).date()
            dist = min((abs((day - f).days) for f in target.focus), default=0)
            return dist, -int(h.get("points") or 0), i
        return [d for _, (_, d) in sorted(enumerate(hits), key=key)][:cap]

    def collect(self, target: Target) -> list[ev.Evidence]:
        now = self._clock()
        stories: list[_Hit] = []
        for h in self._search(target, query=f"github.com/{target.full_name}", tags="story", url_only=True):
            if not _valid(h, "title"):
                continue
            body = strip_html(str(h.get("story_text") or ""))
            stories.append((h, ev.make(
                url=ITEM + str(h["objectID"]), source="hn", kind="story", title=str(h["title"]),
                text=f"{h['title']}\n\n{body}".strip(), fetched_at=now, published_at=str(h["created_at"]),
                extra={"points": int(h.get("points") or 0), "comments": int(h.get("num_comments") or 0),
                       "author": h.get("author"), "linked_url": h.get("url")})))

        word = re.compile(rf"(?i)(?<![\w-]){re.escape(target.name)}(?![\w-])")
        comments: list[_Hit] = []
        for h in self._search(target, query=target.name, tags="comment", url_only=False):
            if not _valid(h, "comment_text"):
                continue
            text = strip_html(str(h["comment_text"]))
            if not word.search(text):
                continue
            title = f"HN 댓글 — {h['story_title']}" if h.get("story_title") else "HN 댓글"
            comments.append((h, ev.make(
                url=ITEM + str(h["objectID"]), source="hn", kind="comment", title=title, text=text,
                fetched_at=now, published_at=str(h["created_at"]),
                extra={"author": h.get("author"), "story_id": h.get("story_id")})))
        return (self._order(target, stories, self.max_stories)
                + self._order(target, comments, self.max_comments))


def _valid(h: dict[str, Any], text_field: str) -> bool:
    """근거로 쓸 수 있는 hit 인가 — 빠진 값이 있으면 실패로 보지 않고 그 hit 만 건너뛴다."""
    if not all(h.get(k) for k in ("objectID", "created_at", text_field)):
        return False
    try:
        int(h["created_at_i"])
    except (KeyError, TypeError, ValueError):
        return False
    return True
