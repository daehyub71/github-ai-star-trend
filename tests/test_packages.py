"""clients.evidence.packages — 저장소 → 패키지(PyPI·npm) → 다운로드·"패키지 의존 수" (FR-5.4, 결정 44).

저장소 URL 로 ecosyste.ms 를 조회하면 이름만 비슷한 포크 패키지가 섞이고 응답이 수십 MB 다(2026-10-28 실측:
openai-python 11.6MB·포크 9개, vercel/ai 81MB). 그래서 저장소 이름에서 패키지 이름 후보를 만들어 이름으로
조회하고, 그 패키지의 저장소 URL 이 우리 저장소와 같을 때만 쓴다. 다운로드는 PyPI 는 pypistats, npm 은
다운로드 API(주간). 의존 수는 GitHub "Used by" 와 다른 수치라 "패키지 의존 수"로 부르고 출처를 적는다.
"""

import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from startrend.clients.evidence.base import SourceError, Target
from startrend.clients.evidence.packages import PackagesSource, candidates
from startrend.clients.transport import HttpResponse, TransportError

NOW = datetime(2026, 10, 28, 5, 0, tzinfo=UTC)
TARGET = Target(1, "Synth-Lab/agent-kit-python", since=date(2026, 10, 18), until=date(2026, 10, 24))


def _pkg(name: str, eco: str, repo: str, **kw: Any) -> dict[str, Any]:
    reg = {"pypi": f"https://pypi.org/project/{name}/", "npm": f"https://www.npmjs.com/package/{name}"}[eco]
    return {"name": name, "ecosystem": eco, "repository_url": repo, "registry_url": reg,
            "downloads": 120000, "downloads_period": "last-month", "dependent_repos_count": 340,
            "dependent_packages_count": 12, "description": f"{name} package", **kw}


def ok(body: Any) -> HttpResponse:
    return HttpResponse(200, {}, json.dumps(body).encode())


class FakeTransport:
    def __init__(self, lookups: Mapping[tuple[str, str], Any], downloads: Mapping[str, Any] | None = None):
        self.lookups = dict(lookups)
        self.downloads = dict(downloads or {})
        self.urls: list[str] = []

    def __call__(self, method: str, url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
        self.urls.append(url)
        u = urlsplit(url)
        if u.netloc == "packages.ecosyste.ms":
            q = parse_qs(u.query)
            r = self.lookups.get((q["ecosystem"][0], q["name"][0]), ok([]))
        else:
            r = self.downloads.get(unquote(u.path), HttpResponse(404, {}, b"{}"))
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, HttpResponse) else ok(r)


REPO_URL = "https://github.com/synth-lab/agent-kit-python"


def test_packages_candidates_strip_language_affixes():
    assert candidates("Synth-Lab/agent-kit-python", "pypi") == ["agent-kit-python", "agent-kit"]
    assert candidates("o/py-tool", "pypi") == ["py-tool", "tool"]
    assert candidates("Synth-Lab/agent-kit-js", "npm") == [
        "agent-kit-js", "agent-kit", "@synth-lab/agent-kit-js"]


def test_packages_uses_only_packages_that_point_back_to_the_repo():
    fork = _pkg("agent-kit-python", "pypi", "https://github.com/someone-else/agent-kit-python")
    real = _pkg("agent-kit", "pypi", REPO_URL + ".git")
    t = FakeTransport({("pypi", "agent-kit-python"): [fork], ("pypi", "agent-kit"): [real]},
                      {"/api/packages/agent-kit/recent": {"data": {"last_day": 10, "last_week": 7000,
                                                                     "last_month": 30000}}})
    docs = PackagesSource(t, clock=lambda: NOW).collect(TARGET)
    [d] = docs
    assert d.url == "https://pypi.org/project/agent-kit/" and d.source == "package" and d.kind == "package"
    assert d.title == "PyPI agent-kit" and d.text == "agent-kit package"
    assert d.extra["downloads_last_week"] == 7000 and d.extra["downloads_week_source"] == "pypistats.org"
    assert d.extra["downloads_last_month"] == 120000 and d.extra["dependent_repos"] == 340
    assert d.extra["dependent_packages"] == 12 and d.extra["dependents_label"] == "패키지 의존 수"
    assert d.extra["attribution"] == "ecosyste.ms (CC BY-SA 4.0)" and d.extra["partial"] == []


def test_packages_npm_weekly_downloads_and_zero_is_unknown():
    real = _pkg("@synth-lab/agent-kit-python", "npm", REPO_URL)
    t = FakeTransport({("npm", "@synth-lab/agent-kit-python"): [real]},
                      {"/downloads/point/last-week/@synth-lab/agent-kit-python":
                       {"downloads": 0, "start": "2026-10-20", "end": "2026-10-26"}})
    [d] = PackagesSource(t, clock=lambda: NOW).collect(TARGET)
    # npm 은 며칠 늦게 반영되고 0 이 섞인다(부록 C-2) — 0 은 그대로 믿지 않고 모름으로 둔다
    assert d.title == "npm @synth-lab/agent-kit-python" and d.extra["downloads_last_week"] is None
    assert d.extra["downloads_week_source"] == "api.npmjs.org"


def test_packages_no_package_means_no_evidence():
    t = FakeTransport({})
    assert PackagesSource(t, clock=lambda: NOW).collect(TARGET) == []
    assert all("packages.ecosyste.ms" in u for u in t.urls)      # 다운로드는 묻지 않는다


def test_packages_download_failure_keeps_the_package():
    real = _pkg("agent-kit", "pypi", REPO_URL)
    t = FakeTransport({("pypi", "agent-kit"): [real]},
                      {"/api/packages/agent-kit/recent": HttpResponse(429, {}, b"slow down")})
    [d] = PackagesSource(t, clock=lambda: NOW).collect(TARGET)
    assert d.extra["downloads_last_week"] is None and d.extra["partial"] == ["downloads"]


@pytest.mark.parametrize("bad", [HttpResponse(500, {}, b"err"), HttpResponse(200, {}, b"{not json"),
                                 TransportError("GET https://packages.ecosyste.ms: timeout")])
def test_packages_lookup_failure_is_a_source_error(bad):
    t = FakeTransport({("pypi", "agent-kit-python"): bad})
    with pytest.raises(SourceError):
        PackagesSource(t, clock=lambda: NOW).collect(TARGET)


def test_packages_sends_an_identifiable_user_agent():
    seen: list[dict[str, str]] = []

    class Spy(FakeTransport):
        def __call__(self, method: str, url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
            seen.append(dict(headers))
            return super().__call__(method, url, headers, timeout)

    PackagesSource(Spy({}), clock=lambda: NOW).collect(TARGET)
    assert seen and all(h["User-Agent"].startswith("startrend/") and "github.com/" in h["User-Agent"]
                        for h in seen)
