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
        try:
            parsed: object = json.loads(body) if body else None
        except ValueError:             # 파일 보내기(multipart)는 바이트 그대로
            parsed = body
        self.sent.append((method, url, dict(headers), parsed))
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


# --- 그림 올리기 (결정 62) — 파일 업로드 → 이미지 블록 끼우기 → 표시 문단 지우기 ---

def test_notion_live_uploads_a_file_in_two_steps():
    nc, fake, _ = client([ok({"id": "fu-1", "status": "pending"}), ok({"id": "fu-1", "status": "uploaded"})])
    assert nc.upload_file("2.png", b"\x89PNG-bytes", "image/png") == "fu-1"
    method, url, headers, body = fake.sent[0]
    assert (method, url) == ("POST", "https://api.notion.com/v1/file_uploads")
    assert body == {"filename": "2.png", "content_type": "image/png"}
    method, url, headers, body = fake.sent[1]
    assert (method, url) == ("POST", "https://api.notion.com/v1/file_uploads/fu-1/send")
    assert headers["Content-Type"].startswith("multipart/form-data; boundary=")
    assert headers["Notion-Version"] == NOTION_VERSION
    boundary = headers["Content-Type"].split("boundary=", 1)[1]
    assert isinstance(body, bytes) and body.startswith(f"--{boundary}\r\n".encode())
    assert b'Content-Disposition: form-data; name="file"; filename="2.png"\r\n' in body
    assert b"Content-Type: image/png\r\n\r\n\x89PNG-bytes\r\n" in body
    assert body.endswith(f"--{boundary}--\r\n".encode()) and TOKEN.encode() not in body


def test_notion_live_upload_must_end_uploaded():
    nc, _, _ = client([ok({"id": "fu-1", "status": "pending"}), ok({"id": "fu-1", "status": "failed"})])
    with pytest.raises(NotionError, match="failed"):
        nc.upload_file("2.png", b"x", "image/png")


def test_notion_live_lists_children_across_pages():
    para = {"id": "b1", "type": "paragraph",
            "paragraph": {"rich_text": [{"plain_text": "⟦그림 "}, {"plain_text": "gen/2.png⟧"}]}}
    image = {"id": "b2", "type": "image", "image": {"type": "external", "external": {"url": "https://x"}}}
    nc, fake, _ = client([ok({"results": [para], "has_more": True, "next_cursor": "c2"}),
                          ok({"results": [image], "has_more": False, "next_cursor": None})])
    blocks = nc.list_children("p1")
    assert [(b.id, b.type, b.text) for b in blocks] == [("b1", "paragraph", "⟦그림 gen/2.png⟧"),
                                                        ("b2", "image", "")]
    assert fake.sent[0][1] == "https://api.notion.com/v1/blocks/p1/children?page_size=100"
    assert fake.sent[1][1] == "https://api.notion.com/v1/blocks/p1/children?page_size=100&start_cursor=c2"


def test_notion_live_inserts_an_image_after_a_block_then_deletes_the_marker():
    nc, fake, _ = client([ok({"results": [{"id": "b9"}]}), ok({"id": "b1", "in_trash": True})])
    nc.insert_image("p1", "b1", "fu-1", "흐름 그림")
    nc.delete_block("b1")
    method, url, _, body = fake.sent[0]
    assert (method, url) == ("PATCH", "https://api.notion.com/v1/blocks/p1/children")
    assert body == {"children": [{"type": "image", "image": {
        "type": "file_upload", "file_upload": {"id": "fu-1"},
        "caption": [{"type": "text", "text": {"content": "흐름 그림"}}]}}],
        "position": {"type": "after_block", "after_block": {"id": "b1"}}}
    assert fake.sent[1][:2] == ("DELETE", "https://api.notion.com/v1/blocks/b1")
