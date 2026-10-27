"""판정 인터페이스 (SPEC FR-3.1·3.6·3.8·3.10, NFR-7, 결정 45).

DecisionClient 뒤에 Claude · JEV · 혼합 구현을 둔다(D-16). LLMDecider 는 LLMClient(예산 계량기로 감싼 것)를
받아 정해진 형식으로 묻고, **결과 검증은 코드가 한다** — 형식이 틀리거나 분류 체계에 없는 값이면
무엇이 틀렸는지 알려 주고 한 번 더 묻고, 그래도 안 되면 "미분류"로 둔다(FR-3.6).
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any, Protocol

from startrend.clients.llm import LLMClient, LLMRequest
from startrend.core.taxonomy import Taxonomy

PROMPT_FILE = Path(__file__).resolve().parents[1] / "prompts" / "classify.md"
README_CHARS = 4000          # 판정 입력에 넣는 README 앞부분 (MEASURE §7)
MAX_TOKENS = 1024            # 사고 + JSON 약 60 토큰 — effort low 기준, FR-14 로 조정
NONE = "none"


@dataclass(frozen=True)
class RepoInput:
    repo_id: int
    full_name: str
    description: str | None
    topics: tuple[str, ...]
    language: str | None
    readme_head: str


@dataclass(frozen=True)
class Decision:
    status: str                       # "ok" · "unclassified" · "refused"
    is_ai: bool | None = None
    type: str | None = None
    category: str | None = None       # 분류 체계 id
    secondary: str | None = None
    reason: str | None = None
    attempts: int = 0
    error: str | None = None
    confidence: float | None = None   # 확률을 주는 구현(JEV)만 — FR-3.9


class DecisionClient(Protocol):
    def classify(self, item: RepoInput) -> Decision: ...


class MockDecider:
    """표에 있는 판정을 돌려준다. 없으면 미분류."""

    def __init__(self, table: dict[int, Decision]):
        self.table = table
        self.asked: list[int] = []

    def classify(self, item: RepoInput) -> Decision:
        self.asked.append(item.repo_id)
        return self.table.get(item.repo_id, Decision(status="unclassified", error="mock: 표에 없음"))


def user_message(item: RepoInput) -> str:
    topics = ", ".join(item.topics) or "(none)"
    return (f"<repository>\nname: {item.full_name}\ndescription: {item.description or '(none)'}\n"
            f"topics: {topics}\nlanguage: {item.language or '(unknown)'}\n</repository>\n"
            f"<readme_head>\n{item.readme_head[:README_CHARS]}\n</readme_head>")


class LLMDecider:
    def __init__(self, llm: LLMClient, taxonomy: Taxonomy, *, effort: str = "low",
                 max_tokens: int = MAX_TOKENS):
        self.llm = llm
        self.tax = taxonomy
        self.effort = effort
        self.max_tokens = max_tokens
        cats = "\n".join(f"- {c.id} — {c.name} — {c.desc}" for c in taxonomy.categories)
        self.system = Template(PROMPT_FILE.read_text(encoding="utf-8")).substitute(
            version=taxonomy.version, types=", ".join(taxonomy.types), categories=cats)
        self.prompt_hash = hashlib.sha256(self.system.encode("utf-8")).hexdigest()[:16]
        ids = [*taxonomy.ids(), NONE]
        self.schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "is_ai": {"type": "boolean"},
                "type": {"type": "string", "enum": list(taxonomy.types)},
                "category": {"type": "string", "enum": ids},
                "secondary": {"type": "string", "enum": ids},
                "reason": {"type": "string"},
            },
            "required": ["is_ai", "type", "category", "secondary", "reason"],
            "additionalProperties": False,
        }

    def classify(self, item: RepoInput) -> Decision:
        user = user_message(item)
        error = ""
        for attempt in (1, 2):
            text = user if attempt == 1 else (
                f"{user}\n\nYour previous answer was rejected: {error}. Answer again with valid values only.")
            resp = self.llm.complete(LLMRequest(system=self.system, user=text, max_tokens=self.max_tokens,
                                                effort=self.effort, schema=self.schema, purpose="classify"))
            if resp.stop_reason == "refusal":
                return Decision(status="refused", attempts=attempt, error="refusal")
            try:
                return self._validate(resp.text, attempt)
            except ValueError as e:
                error = str(e)
        return Decision(status="unclassified", attempts=2, error=error)

    def _validate(self, text: str, attempt: int) -> Decision:
        try:
            d = json.loads(text)
        except ValueError as e:
            raise ValueError(f"not JSON ({e})") from e
        if not isinstance(d, dict):
            raise ValueError("not a JSON object")
        missing = [k for k in ("is_ai", "type", "category", "secondary") if k not in d]
        if missing:
            raise ValueError(f"missing fields {missing}")
        if not isinstance(d["is_ai"], bool):
            raise ValueError(f"is_ai must be true or false, got {d['is_ai']!r}")
        if d["type"] not in self.tax.types:
            raise ValueError(f"unknown type {d['type']!r}")
        category = None if d["category"] in (None, NONE) else self.tax.resolve(str(d["category"]))
        if d["category"] not in (None, NONE) and category is None:
            raise ValueError(f"unknown category {d['category']!r}")
        secondary = None if d["secondary"] in (None, NONE) else self.tax.resolve(str(d["secondary"]))
        if d["secondary"] not in (None, NONE) and secondary is None:
            raise ValueError(f"unknown secondary category {d['secondary']!r}")
        if d["is_ai"] and category is None:
            raise ValueError("an AI repository needs a category")
        if not d["is_ai"]:
            category = secondary = None
        if secondary == category:
            secondary = None
        reason = d.get("reason")
        return Decision(status="ok", is_ai=d["is_ai"], type=d["type"], category=category, secondary=secondary,
                        reason=str(reason) if reason else None, attempts=attempt)
