"""NFR-14 ① — 기본 테스트 중 네트워크 접속은 차단된다. 이 파일 자체가 차단기의 통제군이다."""

import socket
import urllib.request

import pytest

from tests.harness import NetworkBlocked


def test_harness_network_create_connection_blocked():
    with pytest.raises(NetworkBlocked):
        socket.create_connection(("example.com", 80), timeout=1)


def test_harness_network_dns_blocked():
    with pytest.raises(NetworkBlocked):
        socket.getaddrinfo("example.com", 443)


def test_harness_network_urllib_blocked():
    # urllib 은 OSError 를 URLError 로 감싸지만 차단 예외는 감싸지 않고 그대로 올라와야 한다
    with pytest.raises(NetworkBlocked):
        urllib.request.urlopen("http://example.com", timeout=1)


def test_harness_network_raw_socket_blocked():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(NetworkBlocked):
            s.connect(("127.0.0.1", 9))
    finally:
        s.close()


@pytest.mark.live
def test_harness_network_live_tests_are_not_blocked():
    assert not getattr(socket.create_connection, "_startrend_guard", False)
