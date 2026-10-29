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


class NotionClient(Protocol):
    def create_database(self, parent_page_id: str, title: str,
                        properties: Mapping[str, Any]) -> NotionDatabase: ...

    def create_page(self, data_source_id: str, properties: Mapping[str, Any],
                    markdown: str) -> NotionPage: ...

    def get_page(self, page_id: str) -> NotionPage: ...

    def update_properties(self, page_id: str, properties: Mapping[str, Any]) -> None: ...

    def replace_markdown(self, page_id: str, markdown: str) -> None: ...


def status_name(page: NotionPage, prop: str) -> str | None:
    """status 속성 값의 이름. 비었거나 모양이 다르면 None."""
    v = page.properties.get(prop)
    s = v.get("status") if isinstance(v, Mapping) else None
    name = s.get("name") if isinstance(s, Mapping) else None
    return name if isinstance(name, str) else None


@dataclass
class _Page:
    data_source_id: str
    properties: dict[str, Any]
    markdown: str
    in_trash: bool = False


@dataclass
class MockNotion:
    """메모리 안의 Notion. 속성 이름·형식이 데이터 소스 스키마와 맞지 않으면 실제 API 처럼 400 을 낸다."""

    schemas: dict[str, dict[str, Any]] = field(default_factory=dict)     # data_source_id → properties
    titles: dict[str, str] = field(default_factory=dict)                 # data_source_id → DB 제목
    parents: dict[str, str] = field(default_factory=dict)                # data_source_id → 부모 페이지
    pages: dict[str, _Page] = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list)

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
        self.pages[pid] = _Page(data_source_id, copy.deepcopy(dict(properties)), markdown)
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
        self.calls.append(("replace_markdown", page_id))

    # --- 테스트용: 사용자가 Notion 에서 한 일 ---
    def user_sets(self, page_id: str, prop: str, value: Any) -> None:
        self.pages[page_id].properties[prop] = value

    def user_trashes(self, page_id: str) -> None:
        self.pages[page_id].in_trash = True

    def writes(self) -> list[tuple[str, str]]:
        return [c for c in self.calls if c[0] != "get_page"]
