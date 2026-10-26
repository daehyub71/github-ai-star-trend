"""FR-11.6 — GitHub API 계약 점검. 실제 응답이 파서와 가정에 맞지 않으면 정본에 쓰기 전에 멈춘다."""

import os
from datetime import date
from typing import Any

import pytest

from startrend.clients.github_mock import MockGitHub
from startrend.stages import contract
from tests import synth

TODAY = date(2026, 10, 28)  # 수요일 — 이번 주는 2026-10-25
REPO = "synth-lab/agent-kit"
QUERY = "stars:>=1000"


def _gh(history: list[dict[str, Any]] | None = None, readme: bool = True) -> MockGitHub:
    gh = MockGitHub.from_fixture_dir(synth.FIXTURES / "github")
    gh.add_history(REPO, history if history is not None else synth.history(date(2026, 10, 25), [100] * 35))
    if readme:
        gh.add_readme(REPO, "# agent-kit")
    return gh


def _levels(report: contract.ContractReport) -> dict[str, str]:
    return {p.check: p.level for p in report.problems}


def test_contract_ok_on_well_formed_api():
    report = contract.check_github(_gh(), repo=REPO, query=QUERY, today=TODAY)
    assert report.ok, report.problems
    assert report.problems == ()


def test_contract_counts_calls():
    report = contract.check_github(_gh(), repo=REPO, query=QUERY, today=TODAY)
    assert report.calls == {"repo": 1, "count": 1, "history": 2, "search": 1, "readme": 1}


def test_contract_history_oldest_first_is_error():
    weeks = list(reversed(synth.history(date(2026, 10, 25), [100] * 35)))
    report = contract.check_github(_gh(weeks), repo=REPO, query=QUERY, today=TODAY)
    assert not report.ok
    assert _levels(report)["history.order"] == "error"


def test_contract_history_gap_is_error():
    weeks = synth.history(date(2026, 10, 25), [100] * 35)
    del weeks[3]  # 한 주가 빠짐
    report = contract.check_github(_gh(weeks), repo=REPO, query=QUERY, today=TODAY)
    assert _levels(report)["history.order"] == "error"


def test_contract_future_week_is_error():
    weeks = synth.history(date(2026, 11, 1), [100] * 35)
    report = contract.check_github(_gh(weeks), repo=REPO, query=QUERY, today=TODAY)
    assert _levels(report)["history.future"] == "error"


def test_contract_page_continuity_break_is_error():
    weeks = synth.history(date(2026, 10, 25), [100] * 35)
    weeks[30] = synth.history(date(2026, 1, 4), [100])[0]  # 2쪽 첫 주가 1쪽 끝과 이어지지 않음
    report = contract.check_github(_gh(weeks), repo=REPO, query=QUERY, today=TODAY)
    assert _levels(report)["history.pages"] == "error"


def test_contract_days_sum_mismatch_is_warning_only():
    weeks = synth.history(date(2026, 10, 25), [100] * 35)
    weeks[0]["total"] = 999
    report = contract.check_github(_gh(weeks), repo=REPO, query=QUERY, today=TODAY)
    assert _levels(report)["history.days_sum"] == "warn"
    assert report.ok  # 경고는 실행을 막지 않는다 — probe 가 실제 분포를 잰다


def test_contract_last_saturday_zero_is_warning():
    # 히스토리 API 는 하루 늦게 반영된다(MEASURE §6)
    # — 활발한 저장소의 토요일 값이 0 이면 너무 이르게 실행한 것
    weeks = synth.history(date(2026, 10, 25), [100] * 35)
    weeks[1]["days"] = [20, 20, 20, 20, 10, 10, 0]
    weeks[1]["total"] = 100
    report = contract.check_github(_gh(weeks), repo=REPO, query=QUERY, today=TODAY)
    assert _levels(report)["history.saturday"] == "warn"
    assert report.ok


def test_contract_parse_error_is_reported_not_raised():
    weeks = synth.history(date(2026, 10, 25), [100] * 35)
    weeks[0]["days"] = [1, 2, 3]
    report = contract.check_github(_gh(weeks), repo=REPO, query=QUERY, today=TODAY)
    assert _levels(report)["history.parse"] == "error"


def test_contract_missing_repo_is_error():
    report = contract.check_github(_gh(), repo="nobody/nothing", query=QUERY, today=TODAY)
    assert not report.ok
    assert _levels(report)["repo"] == "error"


def test_contract_empty_search_is_error():
    report = contract.check_github(_gh(), repo=REPO, query="topic:nothing", today=TODAY)
    assert _levels(report)["search"] == "error"


def test_contract_missing_readme_is_fine():
    report = contract.check_github(_gh(readme=False), repo=REPO, query=QUERY, today=TODAY)
    assert report.ok


def test_contract_report_to_dict_is_json_ready():
    d = contract.check_github(_gh(), repo=REPO, query=QUERY, today=TODAY).to_dict()
    assert d["ok"] is True and d["problems"] == [] and d["calls"]["history"] == 2


@pytest.mark.live
def test_contract_live_github():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        pytest.skip("GITHUB_TOKEN 없음")
    from startrend.clients.github_live import LiveGitHub

    report = contract.check_github(LiveGitHub(token), today=date.today())
    assert report.ok, report.to_dict()
