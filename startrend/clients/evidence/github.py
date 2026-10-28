"""GitHub 근거 (SPEC FR-5.1) — README · 최근 릴리스 · 저장소 메타. 비용 0(토큰 한도 안).

- 저장소 근거 1건(URL = 저장소 주소, 본문 = README): 메타 숫자는 extra 에 둔다 — 라이선스·기여자 수·
  상위 1명 비중(핵심 기여자 쏠림)·지난 30일 이슈 열림/닫힘(이슈 처리)·릴리스 주기. 카드 ⑦ 의 숫자는 코드가
  채운다(FR-6.5) — LLM 이 쓰지 않는다. 이슈를 끈 저장소는 이슈 수를 모름(None)으로 둔다 — open_issues 는
  PR 도 세므로 "열린 이슈"로 읽으면 안 된다(2026-10-28 실제 확인: DeepInfer 216 중 PR 211).
- 릴리스마다 근거 1건(URL = 릴리스 페이지, 본문 = 릴리스 노트). 급등일 타임라인(FR-6.3)의 재료다.
- 저장소 자체를 못 받으면 출처 실패(SourceError)다. README·릴리스·기여자·이슈 중 하나가 실패하면 그 값만
  비우고 `partial` 에 적는다 — 부분 실패로 근거 전체를 버리지 않는다(FR-5.7).
"""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any

from startrend.clients.evidence.base import SourceError, Target
from startrend.clients.github import GitHubClient, GitHubError
from startrend.clients.github_parse import GitHubFormatError
from startrend.core import evidence as ev
from startrend.core.models import Contributors, IssueCounts, Release

ISSUE_WINDOW_DAYS = 30
RELEASES_FETCHED = 10       # 주기 계산용
MAX_RELEASE_DOCS = 5        # 근거로 남기는 최근 릴리스
README_CHARS = 20_000


def _iso(t: datetime | None) -> str | None:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if t else None


def release_cadence_days(releases: Sequence[Release]) -> float | None:
    """릴리스 사이 간격(일)의 중앙값. 날짜가 있는 릴리스가 2개보다 적으면 None."""
    days = sorted((r.published_at for r in releases if r.published_at), reverse=True)
    gaps = [(a - b).total_seconds() / 86400 for a, b in zip(days, days[1:], strict=False)]
    return round(median(gaps), 1) if gaps else None


class GitHubSource:
    def __init__(self, gh: GitHubClient, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 max_releases: int = MAX_RELEASE_DOCS):
        self._gh = gh
        self._clock = clock
        self.max_releases = max_releases

    @property
    def name(self) -> str:
        return "github"

    def collect(self, target: Target) -> list[ev.Evidence]:
        now = self._clock()
        try:
            repo = self._gh.get_repo(target.full_name)
        except (GitHubError, GitHubFormatError) as e:
            raise SourceError(f"GitHub 저장소를 받지 못했다: {e}") from e
        partial: list[str] = []

        def part(label: str, call: Callable[[], Any], empty: Any) -> Any:
            try:
                return call()
            except (GitHubError, GitHubFormatError):
                partial.append(label)
                return empty

        readme: str = part("readme", lambda: self._gh.readme(repo.full_name) or "", "")
        releases: list[Release] = part(
            "releases", lambda: self._gh.releases(repo.full_name, per_page=RELEASES_FETCHED), [])
        contrib: Contributors = part("contributors", lambda: self._gh.contributors(repo.full_name),
                                     Contributors(None, None))
        since = target.until - timedelta(days=ISSUE_WINDOW_DAYS)
        issues: IssueCounts | None = None       # 이슈를 끈 저장소는 묻지 않는다 — 0 이 아니라 모름
        if repo.has_issues:
            issues = part("issues", lambda: self._gh.issue_counts(repo.full_name, since), None)

        extra = {
            "license": repo.license, "homepage": repo.homepage, "stars": repo.stars, "forks": repo.forks,
            "open_issues": repo.open_issues, "created_at": _iso(repo.created_at),
            "pushed_at": _iso(repo.pushed_at), "archived": repo.archived, "contributors": contrib.count,
            "top_contributor_share": contrib.top_share, "issues_enabled": repo.has_issues,
            "issues_opened_30d": issues.opened if issues else None,
            "issues_closed_30d": issues.closed if issues else None,
            "releases_seen": len(releases), "release_cadence_days": release_cadence_days(releases),
            "latest_release": releases[0].tag if releases else None, "partial": partial,
        }
        docs = [ev.make(url=f"https://github.com/{repo.full_name}", source="github", kind="repo",
                        title=repo.full_name, text=readme[:README_CHARS], fetched_at=now, extra=extra)]
        for r in releases[:self.max_releases]:
            docs.append(ev.make(url=r.url, source="github", kind="release",
                                title=f"{repo.full_name} {r.name}", text=r.body, fetched_at=now,
                                published_at=_iso(r.published_at),
                                extra={"tag": r.tag, "prerelease": r.prerelease}))
        return docs
