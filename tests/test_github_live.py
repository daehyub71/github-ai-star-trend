"""clients.github_live — HTTP 전송을 주입해 재시도·레이트 리밋을 네트워크 없이 검증한다.

마지막의 live 테스트만 실제 GitHub 를 부른다 (`pytest -m live`, GITHUB_TOKEN 필요).
"""

import json
import os
from collections.abc import Mapping
from datetime import date

import pytest

from startrend.clients.github import GitHubError, NotFound, RateLimited
from startrend.clients.github_live import LiveGitHub
from startrend.clients.transport import HttpResponse, TransportError
from tests import synth

TOKEN = "ghp_test_token_value"


class FakeTransport:
    def __init__(self, responses: list[HttpResponse | Exception]):
        self.responses = list(responses)
        self.requests: list[tuple[str, str, dict[str, str]]] = []

    def __call__(self, method: str, url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
        self.requests.append((method, url, dict(headers)))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class FakeClock:
    def __init__(self, now: float = 1_800_000_000.0):
        self.now = now
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.now += s


def ok(body, headers=None) -> HttpResponse:
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    h = {"x-ratelimit-remaining": "4999", "x-ratelimit-limit": "5000", "x-ratelimit-resource": "core"}
    h.update(headers or {})
    return HttpResponse(200, h, data)


def err(status: int, headers=None, body: bytes = b"{}") -> HttpResponse:
    return HttpResponse(status, headers or {}, body)


def make(responses, clock=None, **kw):
    clock = clock or FakeClock()
    t = FakeTransport(responses)
    return LiveGitHub(TOKEN, transport=t, sleep=clock.sleep, clock=clock.time, **kw), t, clock


def test_github_live_sends_auth_version_and_user_agent():
    gh, t, _ = make([ok({"count": 5})])
    assert gh.star_count("a/b") == 5
    method, url, headers = t.requests[0]
    assert method == "GET"
    assert url == "https://api.github.com/repos/a/b/stargazers/count"
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert headers["X-GitHub-Api-Version"] == "2026-03-10"
    assert headers["User-Agent"].startswith("startrend/")


def test_github_live_search_query_params():
    gh, t, _ = make([ok({"total_count": 0, "incomplete_results": False, "items": []})])
    gh.search_repositories("stars:>=1000 created:>2026-10-01", page=2, per_page=50)
    url = t.requests[0][1]
    assert url.startswith("https://api.github.com/search/repositories?")
    assert "q=stars%3A%3E%3D1000+created%3A%3E2026-10-01" in url
    assert "sort=stars" in url and "order=desc" in url and "per_page=50" in url and "page=2" in url


def test_github_live_history_params_and_parse():
    body = synth.history(date(2026, 10, 25), [10, 20])
    gh, t, _ = make([ok(body)])
    weeks = gh.star_history("a/b", page=3)
    assert "stargazers/history?per_page=30&page=3" in t.requests[0][1]
    assert [w.total for w in weeks] == [10, 20]


def test_github_live_readme_raw_accept_and_404_is_none():
    gh, t, _ = make([ok(b"# hi"), err(404)])
    assert gh.readme("a/b") == "# hi"
    assert t.requests[0][2]["Accept"] == "application/vnd.github.raw+json"
    assert gh.readme("a/c") is None


def test_github_live_404_raises_not_found():
    gh, _, _ = make([err(404)])
    with pytest.raises(NotFound):
        gh.get_repo("a/b")


def test_github_live_waits_for_primary_rate_limit_reset():
    clock = FakeClock(now=1_000.0)
    limited = err(403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1060"})
    gh, _, clock = make([limited, ok({"count": 1})], clock=clock)
    assert gh.star_count("a/b") == 1
    assert clock.slept == [61.0]  # reset 까지 + 1초


def test_github_live_rate_limit_wait_too_long_raises():
    clock = FakeClock(now=1_000.0)
    limited = err(403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "99999"})
    gh, _, _ = make([limited], clock=clock, max_rate_wait=900)
    with pytest.raises(RateLimited) as e:
        gh.star_count("a/b")
    assert e.value.reset_at == 99999


def test_github_live_secondary_rate_limit_retry_after():
    gh, _, clock = make([err(429, {"retry-after": "30"}), ok({"count": 2})])
    assert gh.star_count("a/b") == 2
    assert clock.slept == [30.0]


def test_github_live_retries_5xx_with_backoff():
    gh, _, clock = make([err(502), err(503), ok({"count": 3})])
    assert gh.star_count("a/b") == 3
    assert clock.slept == [1.0, 2.0]


def test_github_live_gives_up_after_max_retries():
    gh, _, _ = make([err(500)] * 4, max_retries=3)
    with pytest.raises(GitHubError) as e:
        gh.star_count("a/b")
    assert e.value.status == 500


def test_github_live_retries_connection_drop_then_succeeds():
    # 회귀(2026-10-27 52주 소급 14시간째): 응답 없이 끊긴 연결(RemoteDisconnected) 하나로 실행 전체가 멈췄다
    drops = [TransportError("GET /x: Remote end closed"), TransportError("again")]
    gh, t, clock = make([*drops, ok({"count": 5})])
    assert gh.star_count("a/b") == 5
    assert clock.slept == [2.0, 4.0]


def test_github_live_connection_errors_exhausted_stop_the_run():
    # 계속 끊기면 저장소 하나의 실패(GitHubError)로 넘기지 않는다 — 불변 주간 파일이 빠진 채 쓰이면 안 된다
    gh, t, clock = make([TransportError("down")] * 7)
    with pytest.raises(TransportError):
        gh.star_count("a/b")
    assert len(t.requests) == 7 and clock.slept == [2.0, 4.0, 8.0, 16.0, 32.0, 64.0]


def test_github_live_422_is_not_retried():
    # 히스토리 API 문서: 422 = 검증 실패 또는 과도한 호출. 조용히 재시도하지 않고 올린다
    gh, t, _ = make([err(422, body=b'{"message":"Validation Failed"}')])
    with pytest.raises(GitHubError) as e:
        gh.star_history("a/b")
    assert e.value.status == 422
    assert len(t.requests) == 1


def test_github_live_errors_never_contain_token():
    gh, _, _ = make([err(500)] * 4, max_retries=3)
    with pytest.raises(GitHubError) as e:
        gh.star_count("a/b")
    assert TOKEN not in str(e.value)
    assert TOKEN not in repr(gh)


def test_github_live_tracks_calls_and_rate_limit():
    gh, _, _ = make([ok({"count": 1}), ok(synth.history(date(2026, 10, 25), [1]))])
    gh.star_count("a/b")
    gh.star_history("a/b")
    assert gh.stats.calls == {"count": 1, "history": 1}
    assert gh.last_rate_limit is not None and gh.last_rate_limit.remaining == 4999


def test_github_live_quotes_path_segments():
    gh, t, _ = make([ok({"count": 1})])
    gh.star_count("a b/c")
    assert "/repos/a%20b/c/" in t.requests[0][1]


@pytest.mark.live
def test_github_live_real_api_history_and_count():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        pytest.skip("GITHUB_TOKEN 없음")
    gh = LiveGitHub(token)
    count = gh.star_count("python/cpython")
    weeks = gh.star_history("python/cpython")
    assert count > 0
    assert 0 < len(weeks) <= 30
    assert weeks[0].week >= weeks[-1].week  # 최신 주 먼저 (문서)
