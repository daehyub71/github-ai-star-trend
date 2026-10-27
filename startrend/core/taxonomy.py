"""분류 체계 (SPEC FR-3.2·3.3·3.4, 결정 20 · 부록 A) — `data/taxonomy.toml` 을 읽고 검사한다.

카테고리의 정체성은 바뀌지 않는 ASCII id 다. 화면·라벨에는 이름(name)을 쓴다.
버전을 올릴 때 [mapping] 에 "v<이전>:<이전 id>" = "<지금 id>" 를 남겨 추이 그래프가 이어지게 한다.
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class TaxonomyError(ValueError):
    """분류 체계 파일이 서로 맞지 않는다 — 고칠 때까지 판정하지 않는다."""


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    desc: str


@dataclass(frozen=True)
class Taxonomy:
    version: int
    types: tuple[str, ...]
    categories: tuple[Category, ...]
    mapping: dict[str, str] = field(default_factory=dict)

    def ids(self) -> list[str]:
        return [c.id for c in self.categories]

    def resolve(self, value: str | None) -> str | None:
        """id 나 이름을 받아 id 를 돌려준다. 모르면 None."""
        if value is None:
            return None
        v = value.strip()
        for c in self.categories:
            if v in (c.id, c.name):
                return c.id
        return None

    def name_of(self, cid: str) -> str:
        return next(c.name for c in self.categories if c.id == cid)

    def map_old(self, key: str) -> str | None:
        """이전 버전 키("v1:old-id") → 지금 id."""
        return self.mapping.get(key)


def load(path: Path) -> Taxonomy:
    d: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    if not isinstance(d.get("version"), int):
        raise TaxonomyError("version 이 없거나 정수가 아니다")
    types = tuple(d.get("types") or ())
    if not types:
        raise TaxonomyError("유형(types)이 비어 있다")
    raw = d.get("category", [])
    cats = tuple(Category(str(c["id"]), str(c["name"]), str(c.get("desc", ""))) for c in raw)
    if not cats:
        raise TaxonomyError("카테고리가 없다")
    ids = [c.id for c in cats]
    names = [c.name for c in cats]
    if len(set(ids)) != len(ids):
        raise TaxonomyError("카테고리 id 가 겹친다")
    if len(set(names)) != len(names):
        raise TaxonomyError("카테고리 이름이 겹친다")
    if any(not i.isascii() or not i for i in ids):
        raise TaxonomyError("카테고리 id 는 비어 있지 않은 ASCII 여야 한다")
    mapping = {str(k): str(v) for k, v in (d.get("mapping") or {}).items()}
    bad = [k for k, v in mapping.items() if v not in ids]
    if bad:
        raise TaxonomyError(f"매핑이 지금 없는 id 를 가리킨다: {bad}")
    return Taxonomy(d["version"], types, cats, mapping)
