"""단계 사이를 오가는 값 객체."""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class Repo:
    id: int  # 정체성. 이름은 바뀔 수 있다 (PLAN 1-5)
    full_name: str
    description: str | None
    topics: tuple[str, ...]
    language: str | None
    stars: int
    forks: int
    open_issues: int
    created_at: datetime
    pushed_at: datetime | None
    archived: bool
    is_fork: bool

    @property
    def owner(self) -> str:
        return self.full_name.split("/", 1)[0]

    @property
    def name(self) -> str:
        return self.full_name.split("/", 1)[1]


@dataclass(frozen=True)
class SearchPage:
    total_count: int
    incomplete_results: bool
    items: tuple[Repo, ...]


@dataclass(frozen=True)
class HistoryWeek:
    week: date  # 주 시작일(일요일)
    total: int
    days: tuple[int, ...]  # 일요일부터 7개
    raw_ts: int  # API 가 준 그대로 — 주 경계 실측(FR-12.7)에 쓴다
    utc_offset_hours: float


@dataclass(frozen=True)
class RateLimit:
    resource: str | None
    limit: int | None
    remaining: int | None
    reset_at: int | None  # 유닉스 초
