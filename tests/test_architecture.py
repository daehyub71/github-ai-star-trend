"""NFR-14 ② — 층 규칙 (PLAN 1-2). 통제군: 검사기가 일부러 만든 위반을 실제로 잡는지 먼저 확인한다."""

from startrend.core.config import PROJECT_ROOT
from tests.harness import check_sources, project_sources

# --- 통제군: 검사기가 위반을 잡는가 ---


def test_architecture_detects_core_importing_clients():
    v = check_sources({"startrend/core/x.py": "from startrend.clients import github\n"})
    assert len(v) == 1 and "core 층은 clients 층" in v[0]


def test_architecture_detects_core_importing_stages():
    v = check_sources({"startrend/core/x.py": "import startrend.stages.rank\n"})
    assert len(v) == 1 and "core 층은 stages 층" in v[0]


def test_architecture_detects_clients_importing_gate():
    v = check_sources({"startrend/clients/x.py": "from startrend.gate import check\n"})
    assert len(v) == 1 and "clients 층은 gate 층" in v[0]


def test_architecture_detects_stage_importing_other_stage():
    v = check_sources({"startrend/stages/rank.py": "from startrend.stages import stars\n"})
    assert len(v) == 1 and "단계끼리 import 금지" in v[0]


def test_architecture_detects_stage_importing_other_stage_module_form():
    v = check_sources({"startrend/stages/rank.py": "import startrend.stages.stars\n"})
    assert len(v) == 1 and "단계끼리 import 금지" in v[0]


def test_architecture_detects_network_outside_transport():
    v = check_sources({"startrend/clients/github_live.py": "import urllib.request\n"})
    assert len(v) == 1 and "네트워크 모듈" in v[0]


def test_architecture_detects_network_from_import():
    v = check_sources({"startrend/stages/evidence.py": "from urllib import request\n"})
    assert len(v) == 1 and "네트워크 모듈" in v[0]


def test_architecture_detects_relative_import():
    v = check_sources({"startrend/core/x.py": "from . import week\n"})
    assert len(v) == 1 and "상대 import" in v[0]


def test_architecture_allows_legal_imports():
    sources = {
        "startrend/clients/transport.py": "import urllib.request\nfrom startrend.core import io\n",
        "startrend/clients/github_live.py": "import urllib.parse\nfrom startrend.clients import github\n",
        "startrend/stages/rank.py": (
            "from startrend.core import week\nfrom startrend.clients.github import GitHubClient\n"
        ),
        "startrend/__main__.py": "from startrend.stages import rank, stars\n",
    }
    assert check_sources(sources) == []


# --- 실제 코드베이스 ---


def test_architecture_project_has_no_violations():
    sources = project_sources(PROJECT_ROOT)
    assert sources, "검사할 소스가 없다 — 경로가 틀렸다"
    assert check_sources(sources) == []
