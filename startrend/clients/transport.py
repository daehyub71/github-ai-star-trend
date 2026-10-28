"""HTTP 전송. 표준 라이브러리 urllib 만 쓴다 (SPEC §4-4).

LiveGitHub 는 이 함수 모양만 알면 되므로, 테스트에서는 가짜 전송을 넣어 네트워크 없이 검증한다.
HTTP 오류 상태도 예외가 아니라 응답으로 돌려준다. 재시도 판단은 호출하는 쪽이 한다.
"""

import base64
import hashlib
import http.client
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]  # 키는 소문자
    body: bytes


class TransportError(Exception):
    """연결 자체가 실패했다 (DNS·타임아웃·응답 없이 끊긴 연결 등)."""


class Transport(Protocol):
    def __call__(self, method: str, url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse: ...


class Poster(Protocol):
    """본문이 있는 POST (검색 API 등). 응답 규칙은 Transport 와 같다."""

    def __call__(self, url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> HttpResponse: ...


def _send(req: urllib.request.Request, timeout: float) -> HttpResponse:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return HttpResponse(resp.status, _lower(resp.headers.items()), resp.read())
    except urllib.error.HTTPError as e:
        return HttpResponse(e.code, _lower(e.headers.items()), e.read())
    # RemoteDisconnected·IncompleteRead 는 URLError 가 아니다 — http.client 예외와 OSError 도 잡는다
    except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
        raise TransportError(f"{req.get_method()} {req.full_url.split('?', 1)[0]}: {e}") from e


class UrllibTransport:
    def __call__(self, method: str, url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
        return _send(urllib.request.Request(url, method=method, headers=dict(headers)), timeout)


class UrllibPoster:
    def __call__(self, url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> HttpResponse:
        return _send(urllib.request.Request(url, data=body, method="POST", headers=dict(headers)), timeout)


def _lower(items: Iterable[tuple[str, str]]) -> dict[str, str]:
    return {k.lower(): v for k, v in items}


class CachingTransport:
    """응답을 파일로 남겨 같은 요청은 다시 보내지 않는다 (probe 재개용, 워크스페이스 원칙 5).

    - 키는 메서드 + URL 만 쓴다. 헤더(토큰)는 키에도 파일에도 들어가지 않는다.
    - 200 과 404 만 저장한다. 404 도 답이다. 5xx·레이트 리밋 같은 일시 오류는 저장하지 않는다.
    - cacheable 이 False 라고 하는 응답(예: Search 의 incomplete_results=true)은 저장하지 않고,
      예전에 저장돼 있었더라도 꺼내 쓰지 않는다.
    - 공개 데이터만 지나가는 용도다. 캐시는 .work/ 아래(gitignore)에 둔다.
    """

    _STORE = (200, 404)

    def __init__(self, inner: Transport, cache_dir: Path,
                 cacheable: Callable[[HttpResponse], bool] | None = None):
        self._inner = inner
        self._dir = cache_dir
        self._cacheable = cacheable or (lambda r: True)
        self.hits = 0
        self.misses = 0
        self.miss_seconds: list[float] = []

    def __call__(self, method: str, url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
        path = self._dir / (hashlib.sha256(f"{method} {url}".encode()).hexdigest() + ".json")
        if path.exists():
            d = json.loads(path.read_text(encoding="utf-8"))
            cached = HttpResponse(d["status"], d["headers"], base64.b64decode(d["body"]))
            if self._cacheable(cached):
                self.hits += 1
                return cached
        started = time.monotonic()
        resp = self._inner(method, url, headers, timeout)
        self.misses += 1
        self.miss_seconds.append(time.monotonic() - started)
        if resp.status in self._STORE and self._cacheable(resp):
            self._dir.mkdir(parents=True, exist_ok=True)
            d = {"status": resp.status, "headers": dict(resp.headers), "url": url,
                 "body": base64.b64encode(resp.body).decode("ascii")}
            path.write_text(json.dumps(d), encoding="utf-8")
        return resp
