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
    license: str | None = None      # SPDX id (예: MIT) — 카드 ⑦ (FR-5.1)
    homepage: str | None = None
    has_issues: bool = True         # 이슈를 끈 저장소도 있다 — open_issues 는 PR 도 센다

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
class Release:
    tag: str
    name: str                        # 이름이 없으면 태그
    published_at: datetime | None
    url: str
    body: str
    prerelease: bool


@dataclass(frozen=True)
class Contributors:
    count: int | None                # None — GitHub 이 목록을 주지 않는다(기록이 너무 큰 저장소)
    top_share: float | None          # 상위 1명의 기여 비중 — 첫 100명 기준


@dataclass(frozen=True)
class IssueCounts:
    opened: int                      # 기간 안에 열린 이슈
    closed: int                      # 기간 안에 닫힌 이슈


@dataclass(frozen=True)
class RateLimit:
    resource: str | None
    limit: int | None
    remaining: int | None
    reset_at: int | None  # 유닉스 초
