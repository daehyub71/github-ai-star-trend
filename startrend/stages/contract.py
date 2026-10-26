"""API 계약 점검 (SPEC FR-11.6). 주간 실행의 첫 단계다.

실제 GitHub 응답이 우리 파서와 가정에 맞는지 확인한다. 오류가 하나라도 있으면 주간 실행은
정본에 아무것도 쓰지 않고 멈춘다 — 신규 히스토리 API 의 형식 변경(R2)이 데이터를 오염시키기 전에.

- error: 가정이 깨졌다. 실행을 막는다.
- warn : 확인이 필요하지만 실행은 막지 않는다 (probe 가 실제 분포를 잰다).
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any, Literal

from startrend.clients.github import HISTORY_PER_PAGE_MAX, GitHubClient, GitHubError
from startrend.clients.github_parse import GitHubFormatError
from startrend.core import week
from startrend.core.models import HistoryWeek

DEFAULT_REPO = "python/cpython"  # 크고 오래된 저장소 — 히스토리가 2쪽 이상 있다
DEFAULT_QUERY = "stars:>=100000"

Level = Literal["error", "warn"]
Report = Callable[[str, str], None]  # (check, detail)


@dataclass(frozen=True)
class Problem:
    level: Level
    check: str
    detail: str


@dataclass(frozen=True)
class ContractReport:
    problems: tuple[Problem, ...]
    calls: dict[str, int]

    @property
    def ok(self) -> bool:
        return not any(p.level == "error" for p in self.problems)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "problems": [asdict(p) for p in self.problems], "calls": self.calls}


def check_github(gh: GitHubClient, *, repo: str = DEFAULT_REPO, query: str = DEFAULT_QUERY,
                 today: date) -> ContractReport:
    before = Counter(gh.stats.calls)
    problems: list[Problem] = []

    def error(check: str, detail: str) -> None:
        problems.append(Problem("error", check, detail))

    def warn(check: str, detail: str) -> None:
        problems.append(Problem("warn", check, detail))

    # 저장소 · 스타 수
    try:
        gh.get_repo(repo)
    except (GitHubError, GitHubFormatError) as e:
        error("repo", str(e))
    try:
        if gh.star_count(repo) < 0:
            error("count", "스타 수가 음수다")
    except (GitHubError, GitHubFormatError) as e:
        error("count", str(e))

    # 히스토리 1쪽
    page1 = _history(gh, repo, 1, error)
    if page1 is not None:
        if not page1:
            error("history.order", "히스토리가 비어 있다")
        elif len(page1) > HISTORY_PER_PAGE_MAX:
            error("history.order", f"한 쪽에 {len(page1)}주 — 문서상 최대 {HISTORY_PER_PAGE_MAX}주")
        else:
            _check_weeks(page1, today, error, warn)
            # 2쪽이 1쪽 끝에서 이어지는지 (소급이 쪽을 이어 붙이는 데 기댄다)
            if len(page1) == HISTORY_PER_PAGE_MAX:
                page2 = _history(gh, repo, 2, error)
                if page2:
                    expected = page1[-1].week - timedelta(days=7)
                    if page2[0].week != expected:
                        error("history.pages", f"2쪽 첫 주 {page2[0].week} — 기대값 {expected}")

    # 검색
    try:
        page = gh.search_repositories(query, per_page=5)
        if page.total_count < 1 or not page.items:
            error("search", f"'{query}' 결과가 없다")
        elif page.incomplete_results:
            warn("search", "incomplete_results=true")
    except (GitHubError, GitHubFormatError) as e:
        error("search", str(e))

    # README (없을 수 있다 — None 은 정상)
    try:
        gh.readme(repo)
    except (GitHubError, GitHubFormatError) as e:
        error("readme", str(e))

    calls = dict(Counter(gh.stats.calls) - before)
    return ContractReport(tuple(problems), calls)


def _history(gh: GitHubClient, repo: str, page: int, error: Report) -> list[HistoryWeek] | None:
    try:
        return gh.star_history(repo, page=page)
    except GitHubFormatError as e:
        error("history.parse", str(e))
    except GitHubError as e:
        error("history.fetch", str(e))
    return None


def _check_weeks(weeks: list[HistoryWeek], today: date, error: Report, warn: Report) -> None:
    for prev, cur in zip(weeks, weeks[1:], strict=False):
        if cur.week >= prev.week:
            error("history.order", f"최신 주 먼저가 아니다: {prev.week} 다음에 {cur.week}")
            break
        if prev.week - cur.week != timedelta(days=7):
            error("history.order", f"주 간격이 7일이 아니다: {prev.week} → {cur.week}")
            break
    if weeks[0].week > week.week_start(today):
        error("history.future", f"가장 최근 주 {weeks[0].week} 가 이번 주({week.week_start(today)})보다 뒤다")
    # 주간 실행 시각 안전장치 — 히스토리는 하루 늦게 반영된다(MEASURE §6)
    last = week.week_start(today) - timedelta(days=7)
    last_week = next((w for w in weeks if w.week == last), None)
    if last_week is None:
        warn("history.saturday", f"막 끝난 주({last})가 응답에 없다")
    elif last_week.days[6] == 0:
        warn("history.saturday", f"막 끝난 주({last})의 토요일 값이 0 — 아직 반영 전일 수 있다")
    mismatched = [w.week for w in weeks if sum(w.days) != w.total]
    if mismatched:
        warn("history.days_sum", f"days 합 ≠ total 인 주 {len(mismatched)}개 (예: {mismatched[0]})")
