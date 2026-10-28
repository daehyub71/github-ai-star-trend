"""clients.github_parse — API JSON → 모델. mock 과 live 가 같은 파서를 쓴다."""

import json
from datetime import UTC, date, datetime

import pytest

from startrend.clients import github_parse as gp
from tests import synth

FIX = synth.FIXTURES / "github"


def _repos():
    return json.loads((FIX / "repos.json").read_text(encoding="utf-8"))


def test_github_parse_repo_fields():
    r = gp.parse_repo(_repos()[0])
    assert r.id == 900001
    assert r.full_name == "synth-lab/agent-kit"
    assert r.owner == "synth-lab" and r.name == "agent-kit"
    assert r.topics == ("llm", "agents")
    assert r.stars == 48210 and r.forks == 3120 and r.open_issues == 210
    assert r.created_at == datetime(2025, 3, 2, 10, 0, tzinfo=UTC)
    assert r.archived is False and r.is_fork is False


def test_github_parse_repo_nullable_fields():
    r = gp.parse_repo(_repos()[2])
    assert r.language is None
    assert r.pushed_at is None
    assert r.topics == ()


def test_github_parse_repo_license_and_homepage():
    raw = {**synth.repo("o/r", id=1, stars=10), "license": {"spdx_id": "MIT", "name": "MIT License"},
           "homepage": "https://o.dev"}
    r = gp.parse_repo(raw)
    assert r.license == "MIT" and r.homepage == "https://o.dev"
    bare = gp.parse_repo({**synth.repo("o/r", id=1, stars=10), "license": None, "homepage": ""})
    assert bare.license is None and bare.homepage is None
    assert bare.has_issues is True                       # 필드가 없으면 켜져 있다고 본다(API 기본값)
    assert gp.parse_repo({**synth.repo("o/r", id=1, stars=10), "has_issues": False}).has_issues is False


def test_github_parse_releases_skips_drafts():
    raw = [
        {"tag_name": "v2.0", "name": "Two", "published_at": "2026-10-20T01:00:00Z", "draft": False,
         "prerelease": False, "html_url": "https://github.com/o/r/releases/tag/v2.0", "body": "notes"},
        {"tag_name": "v2.1-rc", "name": None, "published_at": None, "draft": True, "prerelease": True,
         "html_url": "https://github.com/o/r/releases/tag/untagged-1", "body": None},
        {"tag_name": "v1.0", "name": "", "published_at": "2026-09-01T00:00:00Z", "draft": False,
         "prerelease": True, "html_url": "https://github.com/o/r/releases/tag/v1.0", "body": None},
    ]
    rs = gp.parse_releases(raw)
    assert [r.tag for r in rs] == ["v2.0", "v1.0"]
    assert rs[0].name == "Two" and rs[0].published_at == datetime(2026, 10, 20, 1, 0, tzinfo=UTC)
    assert rs[1].name == "v1.0" and rs[1].body == "" and rs[1].prerelease is True
    with pytest.raises(gp.GitHubFormatError):
        gp.parse_releases({"message": "x"})


@pytest.mark.parametrize("link, want", [
    ('<https://api.github.com/repositories/1/contributors?per_page=1&page=2>; rel="next", '
     '<https://api.github.com/repositories/1/contributors?per_page=1&page=347>; rel="last"', 347),
    ('<https://api.github.com/x?page=1>; rel="prev"', None),
    ("", None),
])
def test_github_parse_last_page_from_link_header(link, want):
    assert gp.last_page(link) == want


def test_github_parse_repo_missing_topics_key():
    raw = dict(_repos()[0])
    del raw["topics"]
    assert gp.parse_repo(raw).topics == ()


def test_github_parse_repo_missing_required_raises():
    raw = dict(_repos()[0])
    del raw["id"]
    with pytest.raises(gp.GitHubFormatError):
        gp.parse_repo(raw)


def test_github_parse_search_page():
    page = gp.parse_search_page({"total_count": 3, "incomplete_results": False, "items": _repos()})
    assert page.total_count == 3
    assert page.incomplete_results is False
    assert [r.id for r in page.items] == [900001, 900002, 900003]


def test_github_parse_history_newest_first():
    raw = json.loads((FIX / "history" / "synth-lab__mcp-files.json").read_text(encoding="utf-8"))
    weeks = gp.parse_history(raw)
    assert [w.week for w in weeks] == [date(2026, 10, 25), date(2026, 10, 18), date(2026, 10, 11)]
    assert weeks[0].total == 1100
    assert weeks[0].days == (400, 300, 150, 100, 80, 40, 30)


def test_github_parse_history_kst_aligned_boundary():
    raw = synth.history(date(2026, 10, 25), [70], utc_offset_hours=9)
    w = gp.parse_history(raw)[0]
    assert w.week == date(2026, 10, 25)
    assert w.utc_offset_hours == 9.0


def test_github_parse_history_rejects_bad_days_length():
    with pytest.raises(gp.GitHubFormatError):
        gp.parse_history([{"week": synth.sunday_ts(date(2026, 10, 25)), "total": 1, "days": [1, 0, 0]}])


def test_github_parse_history_rejects_non_list():
    with pytest.raises(gp.GitHubFormatError):
        gp.parse_history({"week": 1})


def test_github_parse_rate_limit_headers():
    rl = gp.parse_rate_limit({
        "x-ratelimit-limit": "5000",
        "x-ratelimit-remaining": "4999",
        "x-ratelimit-reset": "1792886400",
        "x-ratelimit-resource": "core",
    })
    assert (rl.limit, rl.remaining, rl.reset_at, rl.resource) == (5000, 4999, 1792886400, "core")


def test_github_parse_rate_limit_missing_headers():
    rl = gp.parse_rate_limit({})
    assert rl.limit is None and rl.remaining is None
