"""LiveNotion — 가짜 전송으로 요청 모양·재시도·요청 간격을 검사한다 (SPEC FR-15.6, 부록 C-3). 네트워크 0."""

import json
import os
from collections.abc import Mapping

import pytest

from startrend.clients.notion import NOTION_VERSION, NotionError
from startrend.clients.notion_live import LiveNotion
from startrend.clients.transport import HttpResponse, TransportError

TOKEN = "ntn_test_token_value_1234567890"


class FakeRequester:
    def __init__(self, responses: list[HttpResponse | Exception]):
        self.responses = list(responses)
        self.sent: list[tuple[str, str, dict[str, str], object]] = []

    def __call__(self, method: str, url: str, headers: Mapping[str, str], body: bytes | None,
                 timeout: float) -> HttpResponse:
        self.sent.append((method, url, dict(headers), json.loads(body) if body else None))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.now += s


def ok(body: dict[str, object], status: int = 200, headers: dict[str, str] | None = None) -> HttpResponse:
    return HttpResponse(status, headers or {}, json.dumps(body).encode())


def client(responses: list[HttpResponse | Exception]) -> tuple[LiveNotion, FakeRequester, Clock]:
    fake, clock = FakeRequester(responses), Clock()
    nc = LiveNotion(TOKEN, requester=fake, sleep=clock.sleep, clock=clock.time, rand=lambda: 0.0)
    return nc, fake, clock


def test_notion_live_sends_version_token_and_json():
    nc, fake, _ = client([ok({"id": "p1", "url": "https://www.notion.so/p1", "properties": {}})])
    nc.get_page("p1")
    method, url, headers, body = fake.sent[0]
    assert (method, url) == ("GET", "https://api.notion.com/v1/pages/p1")
    assert headers["Notion-Version"] == NOTION_VERSION == "2026-03-11"
    assert headers["Authorization"] == f"Bearer {TOKEN}" and body is None


def test_notion_live_create_database_shape_and_ids():
    props: dict[str, object] = {"이름": {"title": {}}}
    nc, fake, _ = client([ok({"id": "db1", "url": "https://www.notion.so/db1",
                              "data_sources": [{"id": "ds1", "name": "주간"}]})])
    db = nc.create_database("parent-1", "주간", props)
    method, url, _, body = fake.sent[0]
    assert (method, url) == ("POST", "https://api.notion.com/v1/databases")
    assert body == {"parent": {"type": "page_id", "page_id": "parent-1"},
                    "title": [{"type": "text", "text": {"content": "주간"}}],
                    "initial_data_source": {"properties": props}}
    assert (db.id, db.data_source_id, db.url) == ("db1", "ds1", "https://www.notion.so/db1")


def test_notion_live_create_page_with_markdown():
    nc, fake, _ = client([ok({"id": "p1", "url": "https://www.notion.so/p1", "properties": {}})])
    page = nc.create_page("ds1", {"이름": {"title": [{"text": {"content": "x"}}]}}, "# 제목\n\n본문")
    _, url, _, body = fake.sent[0]
    assert url == "https://api.notion.com/v1/pages"
    assert body == {"parent": {"type": "data_source_id", "data_source_id": "ds1"},
                    "properties": {"이름": {"title": [{"text": {"content": "x"}}]}},
                    "markdown": "# 제목\n\n본문"}
    assert page.id == "p1"


def test_notion_live_replace_markdown_never_deletes_child_pages():
    nc, fake, _ = client([ok({"object": "page_markdown", "id": "p1", "markdown": "x", "truncated": False})])
    nc.replace_markdown("p1", "새 본문")
    method, url, _, body = fake.sent[0]
    assert (method, url) == ("PATCH", "https://api.notion.com/v1/pages/p1/markdown")
    assert body == {"type": "replace_content",
                    "replace_content": {"new_str": "새 본문", "allow_deleting_content": False}}


def test_notion_live_update_properties_and_trash_flag():
    nc, fake, _ = client([ok({"id": "p1"}),
                          ok({"id": "p1", "url": "u", "properties": {}, "in_trash": True})])
    nc.update_properties("p1", {"상태": {"status": {"name": "초안"}}})
    assert fake.sent[0][0] == "PATCH"
    assert fake.sent[0][3] == {"properties": {"상태": {"status": {"name": "초안"}}}}
    assert nc.get_page("p1").in_trash is True


def test_notion_live_keeps_requests_under_three_per_second():
    nc, _, clock = client([ok({"id": "a", "properties": {}}), ok({"id": "b", "properties": {}})])
    nc.get_page("a")
    nc.get_page("b")
    assert clock.slept and sum(clock.slept) >= 0.34 - 1e-9


def test_notion_live_waits_retry_after_on_429():
    nc, fake, clock = client([ok({"object": "error", "code": "rate_limited"}, 429, {"retry-after": "7"}),
                              ok({"id": "p1", "properties": {}})])
    assert nc.get_page("p1").id == "p1"
    assert 7.0 in clock.slept and len(fake.sent) == 2


def test_notion_live_retries_server_errors_then_gives_up():
    errs: list[HttpResponse | Exception] = [ok({"object": "error", "code": "internal_server_error"}, 503)] * 7
    nc, fake, _ = client(errs)
    with pytest.raises(NotionError) as e:
        nc.get_page("p1")
    assert e.value.status == 503 and len(fake.sent) == 7


def test_notion_live_retries_transport_errors():
    nc, fake, _ = client([TransportError("reset"), ok({"id": "p1", "properties": {}})])
    assert nc.get_page("p1").id == "p1" and len(fake.sent) == 2


def test_notion_live_client_errors_fail_fast_without_the_token():
    nc, fake, _ = client([ok({"object": "error", "status": 400, "code": "validation_error",
                              "message": "상태 is not a property"}, 400)])
    with pytest.raises(NotionError) as e:
        nc.update_properties("p1", {})
    assert len(fake.sent) == 1 and e.value.code == "validation_error" and e.value.status == 400
    assert TOKEN not in str(e.value) and TOKEN not in repr(nc)


@pytest.mark.live
def test_notion_live_reads_the_parent_page():
    token = os.environ.get("NOTION_TOKEN", "")
    if not token:
        pytest.skip("NOTION_TOKEN 없음")
    page = LiveNotion(token).get_page("405cb5c3-2bc1-80d1-a8d1-d7da9d11b4c6")
    assert page.id.replace("-", "") == "405cb5c32bc180d1a8d1d7da9d11b4c6"
