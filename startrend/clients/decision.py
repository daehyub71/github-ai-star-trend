"""판정 인터페이스 (SPEC FR-3.1·3.6·3.8·3.10, NFR-7, 결정 45).

DecisionClient 뒤에 Claude · JEV · 혼합 구현을 둔다(D-16). LLMDecider 는 LLMClient(예산 계량기로 감싼 것)를
받아 정해진 형식으로 묻고, **결과 검증은 코드가 한다** — 형식이 틀리거나 분류 체계에 없는 값이면
무엇이 틀렸는지 알려 주고 한 번 더 묻고, 그래도 안 되면 "미분류"로 둔다(FR-3.6).

묶음 판정(classify_many, FR-3.7): 1차 Batch → 형식이 틀린 건만 2차 Batch 로 다시 묻는다. 거절(refusal)과
Batch 오류는 일반 호출(대체 모델 — FR-3.10 ③)로 다시 보낸다. 판정이 하나 끝날 때마다 on_decision 으로 알려
부른 쪽이 바로 저장한다 — 다음 묶음이 예산에 걸려도 이미 돈을 낸 결과는 남는다.
"""

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any, Protocol

from startrend.clients.llm import BatchItem, LLMClient, LLMRequest, request_tokens
from startrend.core import untrusted
from startrend.core.taxonomy import Taxonomy

# (custom_id → 요청, 묶음 번호) → custom_id → 결과. 예산·상태 파일은 부른 쪽(budget.run_batch)이 맡는다
BatchRunner = Callable[[dict[str, LLMRequest], str], dict[str, BatchItem]]
OnDecision = Callable[["RepoInput", "Decision"], None]

PROMPT_FILE = Path(__file__).resolve().parents[1] / "prompts" / "classify.md"
README_CHARS = 4000          # 판정 입력에 넣는 README 앞부분 (MEASURE §7)
MAX_TOKENS = 1024            # 사고 + JSON 약 60 토큰 — effort low 기준, FR-14 로 조정
TYPICAL_OUTPUT = 80          # dry-run 하한: 실측 출력 중앙값 79 · p90 92 · 최대 109 (MEASURE §18, effort low)
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
    # 판정에 영향을 주는 것(프롬프트·모델·effort)의 지문. 바뀌면 이전 판정을 다시 쓰지 않는다(FR-3.5)
    @property
    def fingerprint(self) -> str: ...

    def classify(self, item: RepoInput) -> Decision: ...

    def classify_many(self, items: Sequence[RepoInput], *, batch: BatchRunner | None = None,
                      on_decision: OnDecision | None = None) -> dict[int, Decision]: ...


def _one_by_one(decider: DecisionClient, items: Sequence[RepoInput],
                on_decision: OnDecision | None) -> dict[int, Decision]:
    out: dict[int, Decision] = {}
    for it in items:
        out[it.repo_id] = d = decider.classify(it)
        if on_decision:
            on_decision(it, d)
    return out


class MockDecider:
    """표에 있는 판정을 돌려준다. 없으면 미분류."""

    def __init__(self, table: dict[int, Decision]):
        self.table = table
        self.asked: list[int] = []

    @property
    def fingerprint(self) -> str:
        return "mock"

    def classify(self, item: RepoInput) -> Decision:
        self.asked.append(item.repo_id)
        return self.table.get(item.repo_id, Decision(status="unclassified", error="mock: 표에 없음"))

    def classify_many(self, items: Sequence[RepoInput], *, batch: BatchRunner | None = None,
                      on_decision: OnDecision | None = None) -> dict[int, Decision]:
        return _one_by_one(self, items, on_decision)


def user_message(item: RepoInput) -> str:
    # 외부 글이 우리 태그를 닫고 빠져나오지 못하게 한다 (NFR-7, P3-12)
    topics = ", ".join(item.topics) or "(none)"
    repo = (f"name: {item.full_name}\ndescription: {item.description or '(none)'}\n"
            f"topics: {topics}\nlanguage: {item.language or '(unknown)'}")
    readme = untrusted.block("readme_head", item.readme_head[:README_CHARS])
    return f"{untrusted.block('repository', repo)}\n{readme}"


def input_token_range(system: str) -> tuple[int, int]:
    """dry-run 용 1건 입력 토큰 (보통, 보수적) — README 를 꽉 채운 견본, 정해진 형식 몫 포함 (P2-15)."""
    sample = RepoInput(0, "owner/repository-name", "x" * 120, ("topic",) * 6, "Python", "x" * README_CHARS)
    user = user_message(sample)
    return (request_tokens(system, user, schema=True, typical=True),
            request_tokens(system, user, schema=True))


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

    @property
    def fingerprint(self) -> str:
        return f"{self.prompt_hash}:{self.llm.model}:{self.effort}"

    def request(self, item: RepoInput, *, error: str = "") -> LLMRequest:
        """판정 요청. error 가 있으면 두 번째 질문 — 무엇이 틀렸는지 알려 준다."""
        user = user_message(item)
        if error:
            user = (f"{user}\n\nYour previous answer was rejected: {error}. "
                    "Answer again with valid values only.")
        return LLMRequest(system=self.system, user=user, max_tokens=self.max_tokens, effort=self.effort,
                          schema=self.schema, purpose="classify")

    def classify(self, item: RepoInput) -> Decision:
        error = ""
        for attempt in (1, 2):
            resp = self.llm.complete(self.request(item, error=error))
            if resp.stop_reason == "refusal":
                return Decision(status="refused", attempts=attempt, error="refusal")
            try:
                return self._validate(resp.text, attempt)
            except ValueError as e:
                error = str(e)
        return Decision(status="unclassified", attempts=2, error=error)

    def classify_many(self, items: Sequence[RepoInput], *, batch: BatchRunner | None = None,
                      on_decision: OnDecision | None = None) -> dict[int, Decision]:
        if batch is None:
            return _one_by_one(self, items, on_decision)
        done: dict[int, Decision] = {}

        def finish(it: RepoInput, d: Decision) -> None:
            done[it.repo_id] = d
            if on_decision:
                on_decision(it, d)

        by_id = {it.repo_id: it for it in items}
        normal: list[RepoInput] = []    # 거절·Batch 오류 → 일반 호출로 (FR-3.10 ③)
        reask: dict[int, str] = {}
        first = batch({f"r{it.repo_id}-1": self.request(it) for it in items}, "1")
        for it in items:
            res = first.get(f"r{it.repo_id}-1")
            if res is None or res.response is None or res.response.stop_reason == "refusal":
                normal.append(it)
                continue
            try:
                finish(it, self._validate(res.response.text, 1))
            except ValueError as e:
                reask[it.repo_id] = str(e)
        if reask:
            second = batch({f"r{rid}-2": self.request(by_id[rid], error=err)
                            for rid, err in reask.items()}, "2")
            for rid in reask:
                it, res = by_id[rid], second.get(f"r{rid}-2")
                if res is None or res.response is None or res.response.stop_reason == "refusal":
                    normal.append(it)
                    continue
                try:
                    finish(it, self._validate(res.response.text, 2))
                except ValueError as e:
                    finish(it, Decision(status="unclassified", attempts=2, error=str(e)))
        for it in normal:
            finish(it, self.classify(it))
        return done

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
