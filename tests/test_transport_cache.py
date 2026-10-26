"""clients.transport.CachingTransport — probe 를 중간에 끊어도 이미 받은 응답은 다시 부르지 않는다."""

from collections.abc import Mapping

from startrend.clients.transport import CachingTransport, HttpResponse


class Counting:
    def __init__(self, status: int = 200):
        self.calls = 0
        self.status = status

    def __call__(self, method: str, url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
        self.calls += 1
        return HttpResponse(self.status, {"x-ratelimit-remaining": "10"}, f"body:{url}".encode())


def test_transport_cache_hit_skips_network(tmp_path):
    inner = Counting()
    t = CachingTransport(inner, tmp_path)
    a = t("GET", "https://api.github.com/x?q=1", {"Authorization": "Bearer secret"}, 5)
    b = t("GET", "https://api.github.com/x?q=1", {"Authorization": "Bearer secret"}, 5)
    assert inner.calls == 1
    assert a == b
    assert (t.hits, t.misses) == (1, 1)


def test_transport_cache_survives_new_instance(tmp_path):
    inner = Counting()
    CachingTransport(inner, tmp_path)("GET", "https://e/x", {}, 5)
    t2 = CachingTransport(inner, tmp_path)
    t2("GET", "https://e/x", {}, 5)
    assert inner.calls == 1 and t2.hits == 1


def test_transport_cache_keeps_404_but_not_errors(tmp_path):
    nf = Counting(404)
    t = CachingTransport(nf, tmp_path)
    t("GET", "https://e/missing", {}, 5)
    t("GET", "https://e/missing", {}, 5)
    assert nf.calls == 1  # 404 는 답이다 — 캐시한다
    err = Counting(503)
    t = CachingTransport(err, tmp_path)
    t("GET", "https://e/flaky", {}, 5)
    t("GET", "https://e/flaky", {}, 5)
    assert err.calls == 2  # 일시 오류는 캐시하지 않는다


def test_transport_cache_never_stores_secrets(tmp_path):
    t = CachingTransport(Counting(), tmp_path)
    t("GET", "https://e/x", {"Authorization": "Bearer secret-token"}, 5)
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert b"secret-token" not in f.read_bytes()


def test_transport_cache_skips_responses_rejected_by_predicate(tmp_path):
    # 회귀: incomplete_results=true 응답이 캐시에 남아 재실행해도 같은 불완전한 쪽만 받았다
    inner = Counting()
    t = CachingTransport(inner, tmp_path, cacheable=lambda r: b"bad" not in r.body)
    t("GET", "https://e/bad", {}, 5)
    t("GET", "https://e/bad", {}, 5)
    assert inner.calls == 2  # 저장하지 않았다


def test_transport_cache_ignores_previously_stored_rejected_response(tmp_path):
    inner = Counting()
    CachingTransport(inner, tmp_path)("GET", "https://e/bad", {}, 5)  # 예전 판단 기준으로 저장됨
    t = CachingTransport(inner, tmp_path, cacheable=lambda r: b"bad" not in r.body)
    t("GET", "https://e/bad", {}, 5)
    assert inner.calls == 2 and t.hits == 0  # 저장돼 있어도 꺼내 쓰지 않는다


def test_transport_cache_records_miss_latency(tmp_path):
    t = CachingTransport(Counting(), tmp_path)
    t("GET", "https://e/x", {}, 5)
    assert len(t.miss_seconds) == 1
