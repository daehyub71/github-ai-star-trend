"""clients.evidence.github — GitHub 근거: README·최근 릴리스·저장소 메타 (FR-5.1).

메타(라이선스·기여자 수·상위 기여자 비중·이슈 처리·릴리스 주기)는 카드 ⑦ 한계·리스크의 숫자다 — 코드가 채운다
(FR-6.5). 그래서 글이 아니라 저장소 근거의 extra 에 숫자로 둔다. MockGitHub 로 네트워크 없이 검증한다.
"""

from datetime import UTC, date, datetime
from typing import Any

import pytest

from startrend.clients.evidence.base import SourceError, Target
from startrend.clients.evidence.github import GitHubSource, release_cadence_days
from startrend.clients.github import GitHubError
from startrend.clients.github_mock import MockGitHub
from startrend.core import models
from tests import synth

NOW = datetime(2026, 10, 28, 5, 0, tzinfo=UTC)
TARGET = Target(1, "o/r", since=date(2026, 10, 18), until=date(2026, 10, 24))


def _rel(tag: str, day: str, body: str = "notes", draft: bool = False) -> dict[str, Any]:
    return {"tag_name": tag, "name": tag, "published_at": f"{day}T00:00:00Z", "draft": draft,
            "prerelease": False, "html_url": f"https://github.com/o/r/releases/tag/{tag}", "body": body}


def _gh() -> MockGitHub:
    gh = MockGitHub()
    gh.add_repo({**synth.repo("o/r", id=1, stars=5000), "license": {"spdx_id": "Apache-2.0"},
                 "homepage": "https://r.dev"})
    gh.add_readme("o/r", "# r\nA fast agent runtime.")
    gh.add_releases("o/r", [_rel("v1.2", "2026-10-20"), _rel("v1.1", "2026-10-06"),
                            _rel("v1.0", "2026-09-22")])
    gh.add_contributors("o/r", [70, 20, 10])
    gh.add_issue_counts("o/r", models.IssueCounts(opened=40, closed=25))
    return gh


def test_evidence_github_mock_new_endpoints():
    gh = _gh()
    assert [r.tag for r in gh.releases("o/r", per_page=2)] == ["v1.2", "v1.1"]
    assert gh.contributors("o/r") == models.Contributors(3, 0.7)
    assert gh.issue_counts("o/r", date(2026, 9, 27)) == models.IssueCounts(40, 25)
    assert gh.contributors("x/none") == models.Contributors(0, None)


def test_evidence_github_collects_repo_doc_with_meta_and_releases():
    docs = GitHubSource(_gh(), clock=lambda: NOW).collect(TARGET)
    repo, *releases = docs
    assert repo.url == "https://github.com/o/r" and repo.kind == "repo" and repo.source == "github"
    assert repo.text == "# r\nA fast agent runtime."
    assert repo.extra["license"] == "Apache-2.0" and repo.extra["homepage"] == "https://r.dev"
    assert repo.extra["contributors"] == 3 and repo.extra["top_contributor_share"] == 0.7
    assert repo.extra["issues_opened_30d"] == 40 and repo.extra["issues_closed_30d"] == 25
    assert repo.extra["release_cadence_days"] == 14 and repo.extra["releases_seen"] == 3
    assert repo.extra["stars"] == 5000 and repo.extra["open_issues"] == 1
    tags = ("v1.2", "v1.1", "v1.0")
    assert [d.url for d in releases] == [f"https://github.com/o/r/releases/tag/{t}" for t in tags]
    assert releases[0].kind == "release" and releases[0].published_at == "2026-10-20T00:00:00Z"
    assert releases[0].text == "notes"


def test_evidence_github_issue_window_is_30_days_before_the_week_end():
    gh = _gh()
    seen: list[date] = []
    real = gh.issue_counts

    def spy(full_name: str, since: date) -> models.IssueCounts:
        seen.append(since)
        return real(full_name, since)

    gh.issue_counts = spy  # type: ignore[method-assign]
    GitHubSource(gh, clock=lambda: NOW).collect(TARGET)
    assert seen == [date(2026, 9, 24)]


def test_evidence_github_issues_disabled_is_not_zero_activity():
    # 회귀(2026-10-28 실제 확인): deepseek-ai/DeepInfer 는 이슈를 꺼 두었고 open_issues 216 은 거의 PR 이었다.
    # 이슈 검색은 0 을 돌려주는데, 그대로 두면 카드에 "이슈 처리 0"으로 나간다
    # → 모름(None)으로 두고 묻지 않는다
    gh = _gh()
    gh.add_repo({**synth.repo("o/r", id=1, stars=5000), "has_issues": False})
    asked: list[str] = []

    def spy(full_name: str, since: date) -> models.IssueCounts:
        asked.append(full_name)
        return models.IssueCounts(0, 0)

    gh.issue_counts = spy  # type: ignore[method-assign]
    [repo, *_] = GitHubSource(gh, clock=lambda: NOW).collect(TARGET)
    assert asked == [] and repo.extra["issues_enabled"] is False
    assert repo.extra["issues_opened_30d"] is None and repo.extra["issues_closed_30d"] is None


def test_evidence_github_missing_repo_is_a_source_failure():
    with pytest.raises(SourceError):
        GitHubSource(MockGitHub(), clock=lambda: NOW).collect(TARGET)


def test_evidence_github_optional_parts_degrade_instead_of_failing():
    # README 없음·기여자 목록 거부·이슈 검색 실패여도 저장소 근거는 남긴다 — 빈 값은 None
    gh = MockGitHub()
    gh.add_repo(synth.repo("o/r", id=1, stars=10))

    def boom(full_name: str, since: date) -> models.IssueCounts:
        raise GitHubError("search 422", status=422)

    gh.issue_counts = boom  # type: ignore[method-assign]
    [repo] = GitHubSource(gh, clock=lambda: NOW).collect(TARGET)
    assert repo.text == "" and repo.extra["contributors"] == 0 and repo.extra["issues_opened_30d"] is None
    assert repo.extra["release_cadence_days"] is None and repo.extra["partial"] == ["issues"]


def test_evidence_github_release_cadence_is_the_median_gap():
    rs = [models.Release(t, t, datetime(2026, 10, d, tzinfo=UTC), "u", "", False)
          for t, d in (("c", 20), ("b", 13), ("a", 1))]
    assert release_cadence_days(rs) == 9.5
    assert release_cadence_days(rs[:1]) is None
