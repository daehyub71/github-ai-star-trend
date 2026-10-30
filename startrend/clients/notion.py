"""NotionClient 인터페이스 (SPEC FR-15, 부록 C-3). 기본 구현은 MockNotion, 실제 호출은 notion_live.LiveNotion.

단계 코드는 이 모양만 안다. Notion 에서 읽어 온 값(상태·사용자가 고친 글)은 데이터로만 다룬다(NFR-16).
"""

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

NOTION_VERSION = "2026-03-11"   # 부록 C-3 — 고정한다(FR-15.6)


class NotionError(Exception):
    def __init__(self, message: str, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass(frozen=True)
class NotionDatabase:
    id: str
    data_source_id: str
    url: str


@dataclass(frozen=True)
class NotionPage:
    id: str
    url: str
    properties: Mapping[str, Any]
    in_trash: bool = False


@dataclass(frozen=True)
class NotionBlock:
    id: str
    type: str
    text: str                        # rich_text 평문을 이어 붙인 것(이미지 등은 "")


class NotionClient(Protocol):
    def create_database(self, parent_page_id: str, title: str,
                        properties: Mapping[str, Any]) -> NotionDatabase: ...

    def create_page(self, data_source_id: str, properties: Mapping[str, Any],
                    markdown: str) -> NotionPage: ...

    def get_page(self, page_id: str) -> NotionPage: ...

    def update_properties(self, page_id: str, properties: Mapping[str, Any]) -> None: ...

    def replace_markdown(self, page_id: str, markdown: str) -> None: ...

    # 그림 올리기(결정 62) — 마크다운 API 는 올린 파일을 가리킬 수 없어 블록 API 로 끼운다
    def list_children(self, block_id: str) -> list[NotionBlock]: ...

    def upload_file(self, filename: str, data: bytes, content_type: str) -> str: ...

    def insert_image(self, parent_id: str, after_block_id: str, file_upload_id: str,
                     caption: str) -> None: ...

    def delete_block(self, block_id: str) -> None: ...


def status_name(page: NotionPage, prop: str) -> str | None:
    """status 속성 값의 이름. 비었거나 모양이 다르면 None."""
    v = page.properties.get(prop)
    s = v.get("status") if isinstance(v, Mapping) else None
    name = s.get("name") if isinstance(s, Mapping) else None
    return name if isinstance(name, str) else None


@dataclass
class _Block:
    id: str
    type: str
    text: str
    upload: str | None = None        # 이미지 블록이 가리키는 업로드 ID
    caption: str = ""


@dataclass
class _Page:
    data_source_id: str
    properties: dict[str, Any]
    markdown: str
    in_trash: bool = False
    blocks: list[_Block] = field(default_factory=list)


@dataclass
class MockNotion:
    """메모리 안의 Notion. 속성 이름·형식이 데이터 소스 스키마와 맞지 않으면 실제 API 처럼 400 을 낸다."""

    schemas: dict[str, dict[str, Any]] = field(default_factory=dict)     # data_source_id → properties
    titles: dict[str, str] = field(default_factory=dict)                 # data_source_id → DB 제목
    parents: dict[str, str] = field(default_factory=dict)                # data_source_id → 부모 페이지
    pages: dict[str, _Page] = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list)
    uploads: dict[str, tuple[str, bytes, str]] = field(default_factory=dict)  # ID → (파일 이름, 내용, 형식)
    expired: set[str] = field(default_factory=set)
    _blocks: int = 0

    def _parse(self, markdown: str) -> list[_Block]:
        """빈 줄로 나눈 덩어리 하나가 블록 하나 — `![` 로 시작하면 이미지."""
        out = []
        for chunk in (c.strip() for c in markdown.split("\n\n")):
            if chunk:
                self._blocks += 1
                image = chunk.startswith("![")
                kind, text = ("image", "") if image else ("paragraph", chunk)
                out.append(_Block(f"b-{self._blocks}", kind, text))
        return out

    def create_database(self, parent_page_id: str, title: str,
                        properties: Mapping[str, Any]) -> NotionDatabase:
        n = len(self.schemas) + 1
        db = NotionDatabase(f"db-{n}", f"ds-{n}", f"https://www.notion.so/db{n}")
        for name, conf in properties.items():
            rel = conf.get("relation") if isinstance(conf, Mapping) else None
            if rel is not None and rel.get("data_source_id") not in self.schemas:
                raise NotionError(f"{name}: relation 대상 데이터 소스가 없다", 400, "validation_error")
        self.schemas[db.data_source_id] = copy.deepcopy(dict(properties))
        self.titles[db.data_source_id] = title
        self.parents[db.data_source_id] = parent_page_id
        self.calls.append(("create_database", title))
        return db

    def _check(self, data_source_id: str, properties: Mapping[str, Any]) -> None:
        schema = self.schemas.get(data_source_id)
        if schema is None:
            raise NotionError(f"데이터 소스가 없다: {data_source_id}", 404, "object_not_found")
        for name, value in properties.items():
            if name not in schema:
                raise NotionError(f"{name} is not a property that exists.", 400, "validation_error")
            kind = next(iter(k for k in schema[name] if k != "type"))
            if not isinstance(value, Mapping) or kind not in value:
                raise NotionError(f"{name} is expected to be {kind}.", 400, "validation_error")
            if kind == "status" and value["status"] is not None:
                names = {o["name"] for o in schema[name]["status"].get("options", [])}
                if value["status"].get("name") not in names:
                    raise NotionError(f"{name}: 없는 상태 {value['status'].get('name')}", 400,
                                      "validation_error")

    def create_page(self, data_source_id: str, properties: Mapping[str, Any], markdown: str) -> NotionPage:
        self._check(data_source_id, properties)
        pid = f"page-{len(self.pages) + 1}"
        self.pages[pid] = _Page(data_source_id, copy.deepcopy(dict(properties)), markdown,
                                blocks=self._parse(markdown))
        self.calls.append(("create_page", pid))
        return self._view(pid)

    def _view(self, pid: str) -> NotionPage:
        p = self.pages[pid]
        return NotionPage(pid, f"https://www.notion.so/{pid.replace('-', '')}", copy.deepcopy(p.properties),
                          p.in_trash)

    def get_page(self, page_id: str) -> NotionPage:
        if page_id not in self.pages:
            raise NotionError(f"페이지가 없다: {page_id}", 404, "object_not_found")
        self.calls.append(("get_page", page_id))
        return self._view(page_id)

    def update_properties(self, page_id: str, properties: Mapping[str, Any]) -> None:
        p = self.pages[page_id]
        self._check(p.data_source_id, properties)
        p.properties.update(copy.deepcopy(dict(properties)))
        self.calls.append(("update_properties", page_id))

    def replace_markdown(self, page_id: str, markdown: str) -> None:
        self.pages[page_id].markdown = markdown
        self.pages[page_id].blocks = self._parse(markdown)
        self.calls.append(("replace_markdown", page_id))

    def list_children(self, block_id: str) -> list[NotionBlock]:
        self.calls.append(("list_children", block_id))
        return [NotionBlock(b.id, b.type, b.text) for b in self.pages[block_id].blocks]

    def upload_file(self, filename: str, data: bytes, content_type: str) -> str:
        fid = f"up-{len(self.uploads) + 1}"
        self.uploads[fid] = (filename, data, content_type)
        self.calls.append(("upload_file", fid))
        return fid

    def insert_image(self, parent_id: str, after_block_id: str, file_upload_id: str, caption: str) -> None:
        if file_upload_id not in self.uploads or file_upload_id in self.expired:
            raise NotionError(f"쓸 수 없는 파일 업로드: {file_upload_id}", 400, "validation_error")
        blocks = self.pages[parent_id].blocks
        at = next(i for i, b in enumerate(blocks) if b.id == after_block_id)
        self._blocks += 1
        blocks.insert(at + 1, _Block(f"b-{self._blocks}", "image", "", file_upload_id, caption))
        self.calls.append(("insert_image", parent_id))

    def delete_block(self, block_id: str) -> None:
        for p in self.pages.values():
            p.blocks = [b for b in p.blocks if b.id != block_id]
        self.calls.append(("delete_block", block_id))

    # --- 테스트용: 사용자가 Notion 에서 한 일 ---
    def user_sets(self, page_id: str, prop: str, value: Any) -> None:
        self.pages[page_id].properties[prop] = value

    def user_trashes(self, page_id: str) -> None:
        self.pages[page_id].in_trash = True

    def expire_upload(self, file_upload_id: str) -> None:
        """붙이지 못한 채 1시간이 지나 쓸 수 없게 된 업로드."""
        self.expired.add(file_upload_id)

    def writes(self) -> list[tuple[str, str]]:
        return [c for c in self.calls if c[0] not in ("get_page", "list_children")]
