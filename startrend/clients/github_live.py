"""실제 GitHub REST API 클라이언트 (SPEC NFR-10: 인증 토큰, 지수 백오프, 레이트 리밋 준수).

- 토큰은 헤더에만 싣고 예외 메시지·repr 에 남기지 않는다 (NFR-8).
- 1차 레이트 리밋(remaining=0)은 reset 시각까지, 2차 레이트 리밋(retry-after·429)은 지정 시간만큼 기다린다.
  기다릴 시간이 상한을 넘으면 RateLimited 를 올린다 — 무인 실행이 몇 시간씩 멈추지 않게.
- 5xx 는 1·2·4초 지수 백오프로 재시도한다. 422(히스토리 API: 검증 실패 또는 과도한 호출)는 재시도하지 않는다.
- 연결 오류(TransportError)는 2·4·…·64초로 6번 재시도하고, 그래도 안 되면 TransportError 를 그대로 올려
  실행을 멈춘다. 저장소 하나의 실패(GitHubError)로 넘기면 불변 주간 파일이 빠진 채 쓰인다
  — 멈춘 뒤 캐시로 이어 돌린다.
"""

import json
import time
import urllib.parse
from collections.abc import Callable, Mapping
from datetime import date
from typing import Any

from startrend.clients.github import (
    HISTORY_PER_PAGE_MAX,
    CallStats,
    GitHubError,
    NotFound,
    RateLimited,
)
from startrend.clients.github_parse import (
    GitHubFormatError,
    last_page,
    parse_history,
    parse_rate_limit,
    parse_releases,
    parse_repo,
    parse_search_page,
)
from startrend.clients.transport import HttpResponse, Transport, TransportError, UrllibTransport
from startrend.core.models import (
    Contributors,
    HistoryWeek,
    IssueCounts,
    RateLimit,
    Release,
    Repo,
    SearchPage,
)

API_VERSION = "2026-03-10"  # 지원 버전 중 최신 (2026-10 기준 공식 문서)
USER_AGENT = "startrend/0.0.1"
_JSON = "application/vnd.github+json"
_RAW = "application/vnd.github.raw+json"
_SECONDARY_DEFAULT_WAIT = 60.0  # 2차 리밋에 retry-after 가 없으면 1분 기다린다 (GitHub 권고)


class LiveGitHub:
    def __init__(
        self,
        token: str,
        *,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
        base_url: str = "https://api.github.com",
        api_version: str = API_VERSION,
        timeout: float = 30.0,
        max_retries: int = 3,
        max_rate_wait: float = 900.0,
        max_rate_waits: int = 5,
        max_transport_retries: int = 6,
        on_wait: Callable[[float, str], None] | None = None,
    ):
        self._token = token
        self._transport = transport or UrllibTransport()
        self._sleep = sleep
        self._clock = clock
        self._base = base_url.rstrip("/")
        self._api_version = api_version
        self._timeout = timeout
        self._max_retries = max_retries
        self._max_rate_wait = max_rate_wait
        self._max_rate_waits = max_rate_waits
        self._max_transport_retries = max_transport_retries
        self._on_wait = on_wait  # 레이트 리밋 대기마다 (초, 이유) — 로그용
        self.stats = CallStats()
        self.last_rate_limit: RateLimit | None = None

    def __repr__(self) -> str:
        return f"LiveGitHub(base_url={self._base!r}, api_version={self._api_version!r})"

    # --- 엔드포인트 ---

    def get_repo(self, full_name: str) -> Repo:
        return parse_repo(self._json("repo", _repo_path(full_name)))

    def search_repositories(
        self, query: str, *, page: int = 1, per_page: int = 100, sort: str = "stars", order: str = "desc"
    ) -> SearchPage:
        params = {"q": query, "sort": sort, "order": order, "per_page": per_page, "page": page}
        return parse_search_page(self._json("search", "/search/repositories", params))

    def star_history(self, full_name: str, *, page: int = 1, per_page: int = HISTORY_PER_PAGE_MAX
                     ) -> list[HistoryWeek]:
        path = _repo_path(full_name) + "/stargazers/history"
        return parse_history(self._json("history", path, {"per_page": per_page, "page": page}))

    def star_count(self, full_name: str) -> int:
        d = self._json("count", _repo_path(full_name) + "/stargazers/count")
        try:
            return int(d["count"])
        except (KeyError, TypeError, ValueError) as e:
            raise GitHubFormatError(f"스타 수 형식 오류: {e!r}") from e

    def readme(self, full_name: str) -> str | None:
        try:
            resp = self._get("readme", _repo_path(full_name) + "/readme", accept=_RAW)
        except NotFound:
            return None
        return resp.body.decode("utf-8", errors="replace")

    def releases(self, full_name: str, *, per_page: int = 10) -> list[Release]:
        path = _repo_path(full_name) + "/releases"
        return parse_releases(self._json("releases", path, {"per_page": per_page}))

    def contributors(self, full_name: str) -> Contributors:
        """기여자 수는 per_page=1 의 Link 헤더 마지막 쪽으로 센다. 상위 1명 비중은 첫 100명으로 잰다."""
        path = _repo_path(full_name) + "/contributors"
        try:
            first = self._get("contributors", path, {"per_page": 1})
        except GitHubError as e:
            if e.status == 204:                               # 커밋이 없는 저장소
                return Contributors(0, None)
            if e.status == 403 and "too large" in str(e):     # 기록이 너무 큰 저장소 — GitHub 이 주지 않는다
                return Contributors(None, None)
            raise
        try:
            count = last_page(first.headers.get("link")) or len(json.loads(first.body))
        except (ValueError, TypeError) as e:
            raise GitHubFormatError("contributors: 형식이 다르다") from e
        if count <= 1:
            return Contributors(count, 1.0 if count == 1 else None)
        page = self._json("contributors", path, {"per_page": 100})
        try:
            n = [int(c["contributions"]) for c in page]
        except (KeyError, TypeError, ValueError) as e:
            raise GitHubFormatError(f"contributors 형식 오류: {e!r}") from e
        return Contributors(count, round(max(n) / sum(n), 4) if n and sum(n) else None)

    def issue_counts(self, full_name: str, since: date) -> IssueCounts:
        """기간 안에 열린·닫힌 이슈 수 — 이슈 검색 2번(검색은 분당 30회, 레이트 리밋 대기는 _get 이 한다)."""
        out = []
        for qual in ("created", "closed"):
            q = f"repo:{full_name} is:issue {qual}:>={since.isoformat()}"
            d = self._json("search_issues", "/search/issues", {"q": q, "per_page": 1})
            try:
                out.append(int(d["total_count"]))
            except (KeyError, TypeError, ValueError) as e:
                raise GitHubFormatError(f"이슈 검색 형식 오류: {e!r}") from e
        return IssueCounts(opened=out[0], closed=out[1])

    # --- 전송·재시도 ---

    def _json(self, endpoint: str, path: str, params: Mapping[str, object] | None = None) -> Any:
        resp = self._get(endpoint, path, params)
        try:
            return json.loads(resp.body)
        except ValueError as e:
            raise GitHubFormatError(f"{endpoint}: JSON 이 아니다") from e

    def _get(self, endpoint: str, path: str, params: Mapping[str, object] | None = None,
             accept: str = _JSON) -> HttpResponse:
        url = self._base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        headers = {
            "Accept": accept,
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": self._api_version,
            "User-Agent": USER_AGENT,
        }
        retries = 0
        rate_waits = 0
        drops = 0
        while True:
            started = self._clock()
            try:
                resp = self._transport("GET", url, headers, self._timeout)
            except TransportError:
                if drops >= self._max_transport_retries:
                    raise
                drops += 1
                self._sleep(2.0**drops)
                continue
            self.stats.record(endpoint, self._clock() - started)
            if any(k.startswith("x-ratelimit-") for k in resp.headers):
                self.last_rate_limit = parse_rate_limit(resp.headers)

            if resp.status == 200:
                return resp
            if resp.status == 404:
                raise NotFound(f"{endpoint}: {path} 없음", status=404)

            waited = self._rate_limit_wait(resp)
            if waited is not None:
                wait, why = waited
                reset_at = parse_rate_limit(resp.headers).reset_at
                if wait > self._max_rate_wait or rate_waits >= self._max_rate_waits:
                    raise RateLimited(f"{endpoint}: 레이트 리밋 — {wait:.0f}초를 기다려야 한다", reset_at)
                if self._on_wait is not None:
                    self._on_wait(wait, why)
                self._sleep(wait)
                self.stats.rate_waits += wait
                rate_waits += 1
                continue

            if resp.status >= 500 and retries < self._max_retries:
                self._sleep(2.0**retries)
                retries += 1
                continue

            snippet = resp.body[:200].decode("utf-8", errors="replace")
            raise GitHubError(f"{endpoint}: {path} HTTP {resp.status} {snippet}", status=resp.status)

    def _rate_limit_wait(self, resp: HttpResponse) -> tuple[float, str] | None:
        """(기다릴 초, 이유). 기다려도 풀리지 않는 응답이면 None."""
        if resp.status not in (403, 429):
            return None
        retry_after = resp.headers.get("retry-after")
        if retry_after:
            return float(retry_after), f"{resp.status} retry-after"
        if resp.headers.get("x-ratelimit-remaining") == "0":
            reset = int(resp.headers.get("x-ratelimit-reset") or 0)
            return max(reset - self._clock(), 0.0) + 1.0, f"{resp.status} primary limit — reset"
        if resp.status == 429:
            return _SECONDARY_DEFAULT_WAIT, "429 secondary limit — default wait"
        if b"secondary rate limit" in resp.body.lower():  # 헤더 없는 403 2차 리밋 — 최소 1분(GitHub 문서)
            return _SECONDARY_DEFAULT_WAIT, "403 secondary limit — default wait"
        return None  # 권한 문제 등 — 기다려도 풀리지 않는다


def cacheable_response(resp: HttpResponse) -> bool:
    """Search 가 시간 초과로 일부만 준 응답(incomplete_results=true)은 캐시하지 않는다."""
    if b"incomplete_results" not in resp.body:
        return True
    try:
        return not json.loads(resp.body).get("incomplete_results", False)
    except (ValueError, AttributeError):
        return True


def _repo_path(full_name: str) -> str:
    owner, _, name = full_name.partition("/")
    if not owner or not name:
        raise ValueError(f"owner/repo 형식이어야 한다: {full_name!r}")
    q = urllib.parse.quote
    return f"/repos/{q(owner, safe='')}/{q(name, safe='')}"
