"""카드 파일과 최신 카드 보관소 (PLAN 1-4).

analyze 가 쓰고 brief 가 읽는다 — 단계끼리 import 하지 않도록 core 에 둔다.

카드는 앞머리(`---` 사이 key: value) + `## ` 섹션으로 된 마크다운이다. 보관소는 저장소마다 최신 카드와 그때의
상태(스타·README 해시·릴리스·허용 URL·이력)를 둔다 — 결정 53(공개 저장소 밖), 자리는 Phase 5 에서 정한다.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from startrend.core import io


def sections(markdown: str) -> dict[str, str]:
    """`## 제목` → 본문."""
    return {h: b for h, b in re.findall(r"(?ms)^## (.+?)\n(.*?)(?=^## |\Z)", markdown.replace("\r\n", "\n"))}


def front(markdown: str) -> dict[str, str]:
    """카드 앞머리(--- 사이 key: value)."""
    md = markdown.replace("\r\n", "\n")
    if not md.startswith("---"):
        return {}
    return dict(re.findall(r"(?m)^(\w+): (.*)$", md.split("---")[1]))


def summary(markdown: str) -> dict[str, str]:
    """① 3줄 요약 → {"what", "why_now", "meaning"} (없으면 빈 값)."""
    body = sections(markdown).get("① 3줄 요약", "")
    keys = {"무엇인지": "what", "왜 지금 떴나": "why_now", "어떤 의미인지": "meaning"}
    out = {v: "" for v in keys.values()}
    for label, text in re.findall(r"(?m)^- \*\*(.+?)\*\* — (.*)$", body):
        if label in keys:
            out[keys[label]] = text.strip()
    return out


@dataclass
class StoredCard:
    markdown: str
    meta: dict[str, Any]


class CardStore:
    """저장소마다 최신 카드와 상태. 열쇠는 저장소 숫자 ID(이름은 바뀔 수 있다)."""

    def __init__(self, root: Path):
        self.root = root

    def load(self, repo_id: int) -> StoredCard | None:
        md, meta = self.root / f"{repo_id}.md", self.root / f"{repo_id}.json"
        if not (md.exists() and meta.exists()):
            return None
        return StoredCard(io.read_text(md), io.read_json(meta))

    def save(self, repo_id: int, markdown: str, meta: Mapping[str, Any]) -> None:
        io.write_text_atomic(self.root / f"{repo_id}.md", markdown)
        io.write_json(self.root / f"{repo_id}.json", dict(meta))
