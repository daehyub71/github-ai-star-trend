"""저장소 대표 이미지 (결정 60) — 가짜 전송으로 네트워크 0.

주인이 올린 소셜 미리보기(usesCustomOpenGraphImage)만 쓴다. GitHub 이 자동으로 만든 카드는 '없음'으로 본다.
"""

import json
from collections.abc import Mapping

import pytest

from startrend.clients import repo_images as ri
from startrend.clients.transport import HttpResponse


class FakePoster:
    def __init__(self, resp: HttpResponse):
        self.resp = resp
        self.sent: list[tuple[str, dict[str, str], dict[str, object]]] = []

    def __call__(self, url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> HttpResponse:
        self.sent.append((url, dict(headers), json.loads(body)))
        return self.resp


def _gql(data: dict[str, object]) -> HttpResponse:
    return HttpResponse(200, {}, json.dumps({"data": data}).encode())


def test_repo_images_asks_once_and_keeps_only_custom_previews():
    poster = FakePoster(_gql({
        "r0": {"openGraphImageUrl": "https://repository-images.githubusercontent.com/1/a",
               "usesCustomOpenGraphImage": True},
        "r1": {"openGraphImageUrl": "https://opengraph.githubassets.com/x/o/b",
               "usesCustomOpenGraphImage": False},
        "r2": None}))
    out = ri.social_previews(["o/a", "o/b", "o/gone"], "tok", poster=poster)
    assert out == {"o/a": "https://repository-images.githubusercontent.com/1/a"}
    url, headers, body = poster.sent[0]
    assert url == "https://api.github.com/graphql" and headers["Authorization"] == "Bearer tok"
    assert body["variables"] == {"o0": "o", "n0": "a", "o1": "o", "n1": "b", "o2": "o", "n2": "gone"}
    assert "usesCustomOpenGraphImage" in str(body["query"]) and len(poster.sent) == 1


def test_repo_images_raises_on_http_error_without_the_token():
    poster = FakePoster(HttpResponse(401, {}, b'{"message":"Bad credentials"}'))
    with pytest.raises(ri.RepoImageError) as e:
        ri.social_previews(["o/a"], "secret-token-value", poster=poster)
    assert "401" in str(e.value) and "secret-token-value" not in str(e.value)


def test_repo_images_download_checks_type_and_size():
    def transport(body: bytes, ctype: str, status: int = 200):
        return lambda method, url, headers, timeout: HttpResponse(status, {"content-type": ctype}, body)

    data, ext = ri.download("u", transport=transport(b"\x89PNG", "image/png"))
    assert data == b"\x89PNG" and ext == ".png"
    assert ri.download("u", transport=transport(b"x", "image/jpeg; charset=binary"))[1] == ".jpg"
    with pytest.raises(ri.RepoImageError):
        ri.download("u", transport=transport(b"<html>", "text/html"))
    with pytest.raises(ri.RepoImageError):
        ri.download("u", transport=transport(b"x" * (ri.MAX_IMAGE + 1), "image/png"))
    with pytest.raises(ri.RepoImageError):
        ri.download("u", transport=transport(b"", "image/png", 404))
