"""실제 Notion API 클라이언트 (SPEC FR-15.6, 부록 C-3).

- `Notion-Version: 2026-03-11` 고정. 토큰은 헤더에만 싣고 예외 메시지·repr 에 남기지 않는다(NFR-8·NFR-16).
- 요청 한도는 연결당 분당 180회 — 요청 사이를 0.34초 이상 벌려 초당 3회 미만으로 보낸다.
- 429 는 `Retry-After`(헤더, 없으면 본문 `additional_data.retry_after`)만큼 쉰다. 409·5xx·연결 오류는
  지터를 섞은 지수 백오프로 6번까지 다시 보낸다. 그 밖의 4xx 는 다시 보내지 않는다.
- 본문은 마크다운 API 로 넣는다 — 블록을 100개·2,000자로 나눌 일이 없다.
"""

import json
import random
import time
from collections.abc import Callable, Mapping
from typing import Any

from startrend.clients.notion import NOTION_VERSION, NotionDatabase, NotionError, NotionPage
from startrend.clients.transport import HttpResponse, Requester, TransportError, UrllibRequester

MIN_INTERVAL = 0.34      # 초당 3회 미만
_RETRY_STATUS = (409, 500, 502, 503, 504)


class LiveNotion:
    def __init__(self, token: str, *, requester: Requester | None = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                 rand: Callable[[], float] = random.random, base_url: str = "https://api.notion.com",
                 timeout: float = 60.0, max_retries: int = 6, min_interval: float = MIN_INTERVAL):
        self._token = token
        self._req = requester or UrllibRequester()
        self._sleep = sleep
        self._clock = clock
        self._rand = rand
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._min_interval = min_interval
        self._last: float | None = None
        self.calls = 0

    def __repr__(self) -> str:
        return f"LiveNotion(base_url={self._base!r}, calls={self.calls})"

    def _space(self) -> None:
        if self._last is not None:
            wait = self._min_interval - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        self._last = self._clock()

    def _backoff(self, attempt: int) -> float:
        return min(60.0, 2.0 ** attempt) + self._rand() * 0.5

    @staticmethod
    def _retry_after(resp: HttpResponse, body: Mapping[str, Any]) -> float | None:
        for v in (resp.headers.get("retry-after"), (body.get("additional_data") or {}).get("retry_after")):
            try:
                if v is not None:
                    return max(0.0, float(v))
            except (TypeError, ValueError):
                continue
        return None

    def _call(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._token}", "Notion-Version": NOTION_VERSION,
                   "Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        what = f"{method} {path}"
        for attempt in range(self._max_retries + 1):
            self._space()
            try:
                resp = self._req(method, self._base + path, headers, data, self._timeout)
            except TransportError:
                if attempt == self._max_retries:
                    raise
                self._sleep(self._backoff(attempt))
                continue
            self.calls += 1
            try:
                parsed = json.loads(resp.body) if resp.body else {}
            except ValueError:
                parsed = {}
            parsed = parsed if isinstance(parsed, dict) else {}
            if resp.status < 400:
                return parsed
            code, msg = parsed.get("code"), parsed.get("message") or ""
            if attempt < self._max_retries and (resp.status == 429 or resp.status in _RETRY_STATUS):
                wait = self._retry_after(resp, parsed) if resp.status == 429 else None
                self._sleep(wait if wait is not None else self._backoff(attempt))
                continue
            raise NotionError(f"{what}: HTTP {resp.status} {code or ''} {msg}".strip(), resp.status,
                              code if isinstance(code, str) else None)
        raise NotionError(f"{what}: 재시도 한도")      # 도달하지 않는다 — mypy 용

    def create_database(self, parent_page_id: str, title: str,
                        properties: Mapping[str, Any]) -> NotionDatabase:
        d = self._call("POST", "/v1/databases", {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "initial_data_source": {"properties": dict(properties)}})
        sources = d.get("data_sources") or []
        if not sources or not sources[0].get("id"):
            raise NotionError(f"데이터베이스 응답에 data_sources 가 없다: {title}")
        return NotionDatabase(str(d["id"]), str(sources[0]["id"]), str(d.get("url") or ""))

    @staticmethod
    def _page(d: Mapping[str, Any]) -> NotionPage:
        return NotionPage(str(d["id"]), str(d.get("url") or ""), d.get("properties") or {},
                          bool(d.get("in_trash", False)))

    def create_page(self, data_source_id: str, properties: Mapping[str, Any], markdown: str) -> NotionPage:
        return self._page(self._call("POST", "/v1/pages", {
            "parent": {"type": "data_source_id", "data_source_id": data_source_id},
            "properties": dict(properties), "markdown": markdown}))

    def get_page(self, page_id: str) -> NotionPage:
        return self._page(self._call("GET", f"/v1/pages/{page_id}"))

    def update_properties(self, page_id: str, properties: Mapping[str, Any]) -> None:
        self._call("PATCH", f"/v1/pages/{page_id}", {"properties": dict(properties)})

    def replace_markdown(self, page_id: str, markdown: str) -> None:
        self._call("PATCH", f"/v1/pages/{page_id}/markdown", {
            "type": "replace_content",
            "replace_content": {"new_str": markdown, "allow_deleting_content": False}})
