"""clients.github_mock — 기본 테스트 게이트의 GitHub. 실제 API 의 제약(1,000건·30주)을 흉내 낸다."""

from datetime import date

import pytest

from startrend.clients.github import GitHubError, NotFound
from startrend.clients.github_mock import MockGitHub
from tests import synth

FIX = synth.FIXTURES / "github"


@pytest.fixture
def gh():
    return MockGitHub.from_fixture_dir(FIX)


def test_github_mock_get_repo(gh):
    assert gh.get_repo("synth-lab/agent-kit").stars == 48210


def test_github_mock_get_repo_not_found(gh):
    with pytest.raises(NotFound):
        gh.get_repo("nobody/nothing")


def test_github_mock_search_registered_query(gh):
    page = gh.search_repositories("topic:mcp")
    assert page.total_count == 1
    assert [r.full_name for r in page.items] == ["synth-lab/mcp-files"]


def test_github_mock_search_unknown_query_is_empty(gh):
    assert gh.search_repositories("topic:none").total_count == 0


def test_github_mock_search_pagination():
    gh = MockGitHub()
    names = [f"synth/r{i}" for i in range(250)]
    for i, n in enumerate(names):
        gh.add_repo(synth.repo(n, id=i + 1, stars=1000 - i))
    gh.add_search("q", names)
    p3 = gh.search_repositories("q", page=3, per_page=100)
    assert len(p3.items) == 50
    assert p3.items[0].full_name == "synth/r200"


def test_github_mock_search_caps_at_1000_results():
    # 실제 Search API 는 처음 1,000건만 준다 — FR-1.2 의 분할 쿼리가 필요한 이유
    gh = MockGitHub()
    names = [f"synth/r{i}" for i in range(1200)]
    for i, n in enumerate(names):
        gh.add_repo(synth.repo(n, id=i + 1, stars=5000 - i))
    gh.add_search("q", names)
    assert gh.search_repositories("q", page=1, per_page=1).total_count == 1200
    gh.search_repositories("q", page=10, per_page=100)  # 901~1000 은 된다
    with pytest.raises(GitHubError):
        gh.search_repositories("q", page=11, per_page=100)


def _range_mock():
    gh = MockGitHub()
    for i, stars in enumerate([5, 10, 50, 999, 1000, 1500, 2000, 70000]):
        created = "2026-10-20T00:00:00Z" if stars in (10, 1500) else "2024-01-01T00:00:00Z"
        gh.add_repo(synth.repo(f"synth/s{stars}", id=i + 1, stars=stars, created=created))
    return gh


def test_github_mock_search_evaluates_star_range():
    gh = _range_mock()
    page = gh.search_repositories("stars:1000..2000")
    assert [r.stars for r in page.items] == [2000, 1500, 1000]  # 스타 내림차순
    assert gh.search_repositories("stars:>=1500").total_count == 3
    assert gh.search_repositories("stars:>1500").total_count == 2
    assert gh.search_repositories("stars:999").total_count == 1


def test_github_mock_search_evaluates_created_qualifier():
    gh = _range_mock()
    page = gh.search_repositories("created:>=2026-10-01 stars:>=10")
    assert sorted(r.stars for r in page.items) == [10, 1500]


def test_github_mock_search_unknown_qualifier_is_empty():
    assert _range_mock().search_repositories("topic:llm stars:>=1").total_count == 0


def test_github_mock_history_from_fixture(gh):
    weeks = gh.star_history("synth-lab/mcp-files")
    assert weeks[0].week == date(2026, 10, 25)
    assert sum(w.total for w in weeks) == 1830


def test_github_mock_history_pages_of_30():
    gh = MockGitHub()
    gh.add_repo(synth.repo("synth/long", id=1, stars=70 * 35))
    gh.add_history("synth/long", synth.history(date(2026, 10, 25), [70] * 35))
    p1 = gh.star_history("synth/long", page=1)
    p2 = gh.star_history("synth/long", page=2)
    assert len(p1) == 30 and len(p2) == 5
    assert p1[0].week == date(2026, 10, 25)
    assert p2[0].week == p1[-1].week.fromordinal(p1[-1].week.toordinal() - 7)


def test_github_mock_history_beyond_last_page_is_empty(gh):
    assert gh.star_history("synth-lab/mcp-files", page=2) == []


def test_github_mock_star_count(gh):
    assert gh.star_count("synth-lab/mcp-files") == 1830


def test_github_mock_readme(gh):
    assert "Synthetic fixture README" in (gh.readme("synth-lab/mcp-files") or "")
    assert gh.readme("synth-lab/agent-kit") is None


def test_github_mock_counts_calls(gh):
    gh.get_repo("synth-lab/agent-kit")
    gh.star_history("synth-lab/mcp-files")
    gh.star_history("synth-lab/mcp-files", page=2)
    assert gh.stats.calls == {"repo": 1, "history": 2}
