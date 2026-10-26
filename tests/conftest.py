"""공통 픽스처. 기본 테스트 게이트는 네트워크 0 이다 — 약속이 아니라 코드로 막는다 (SPEC NFR-14 ①)."""

import socket
from typing import Any

import pytest

from tests.harness import NetworkBlocked


def _guard(*args: Any, **kwargs: Any) -> Any:
    raise NetworkBlocked(
        "기본 테스트 게이트에서 네트워크 접속 금지 — 실제 호출 테스트는 @pytest.mark.live 로 표시한다"
    )


_guard._startrend_guard = True  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _block_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("live"):
        return
    monkeypatch.setattr(socket.socket, "connect", _guard)
    monkeypatch.setattr(socket.socket, "connect_ex", _guard)
    monkeypatch.setattr(socket, "create_connection", _guard)
    monkeypatch.setattr(socket, "getaddrinfo", _guard)
