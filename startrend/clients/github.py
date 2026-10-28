"""GitHubClient 인터페이스. 기본 구현은 mock 이고, 실제 호출은 github_live.LiveGitHub 다 (SPEC §4-1)."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from startrend.core.models import (
    Contributors,
    HistoryWeek,
    IssueCounts,
    RateLimit,
    Release,
    Repo,
    SearchPage,
)

HISTORY_PER_PAGE_MAX = 30  # 히스토리 API 한도 (공식 문서)
SEARCH_RESULT_CAP = 1000  # Search API 는 처음 1,000건만 준다


class GitHubError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class NotFound(GitHubError):
    pass


class RateLimited(GitHubError):
    def __init__(self, message: str, reset_at: int | None):
        super().__init__(message, status=403)
        self.reset_at = reset_at


@dataclass
class CallStats:
    """엔드포인트별 호출 수와 걸린 시간. probe 가 그대로 보고한다 (FR-12.2)."""

    calls: Counter[str] = field(default_factory=Counter)
    seconds: float = 0.0
    rate_waits: float = 0.0

    def record(self, endpoint: str, elapsed: float) -> None:
        self.calls[endpoint] += 1
        self.seconds += elapsed


class GitHubClient(Protocol):
    stats: CallStats
    last_rate_limit: RateLimit | None

    def get_repo(self, full_name: str) -> Repo: ...

    def search_repositories(
        self, query: str, *, page: int = 1, per_page: int = 100, sort: str = "stars", order: str = "desc"
    ) -> SearchPage: ...

    def star_history(self, full_name: str, *, page: int = 1, per_page: int = HISTORY_PER_PAGE_MAX
                     ) -> list[HistoryWeek]: ...

    def star_count(self, full_name: str) -> int: ...

    def readme(self, full_name: str) -> str | None: ...

    # 근거 수집용 (FR-5.1) — 저장소가 없으면 NotFound
    def releases(self, full_name: str, *, per_page: int = 10) -> list[Release]: ...

    def contributors(self, full_name: str) -> Contributors: ...

    def issue_counts(self, full_name: str, since: date) -> IssueCounts: ...
