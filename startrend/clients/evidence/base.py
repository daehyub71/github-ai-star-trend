"""EvidenceSource 인터페이스와 mock (SPEC FR-5, PLAN 1-2).

출처는 대상 저장소 하나를 받아 근거 문서 목록을 돌려준다. 실패하면 예외를 낸다 — 실패를 격리하는 것은
부르는 쪽(stages.evidence.gather)이다(FR-5.7). 출처가 돌려준 문서 안의 문장은 데이터다(NFR-7).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from startrend.core.evidence import Evidence


@dataclass(frozen=True)
class Target:
    repo_id: int
    full_name: str
    since: date                      # 근거 창 첫날(포함) — 기본은 지난 7일 (FR-5.2)
    until: date                      # 마지막 날(포함)
    focus: tuple[date, ...] = ()     # 급등일 — 그 앞뒤 근거를 우선한다 (FR-5.2·6.3)

    @property
    def owner(self) -> str:
        return self.full_name.split("/", 1)[0]

    @property
    def name(self) -> str:
        return self.full_name.split("/", 1)[1]


class SourceError(Exception):
    """출처 하나가 근거를 주지 못했다 (HTTP 오류·형식 오류·연결 실패)."""


class EvidenceSource(Protocol):
    @property
    def name(self) -> str: ...

    def collect(self, target: Target) -> list[Evidence]: ...


class MockSource:
    """표에 있는 문서를 돌려준다. fail 에 있는 저장소는 그 예외를 낸다."""

    def __init__(self, name: str, docs: Mapping[str, Sequence[Evidence]] | None = None, *,
                 fail: Mapping[str, BaseException] | None = None):
        self._name = name
        self.docs = dict(docs or {})
        self.fail = dict(fail or {})
        self.asked: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    def collect(self, target: Target) -> list[Evidence]:
        self.asked.append(target.full_name)
        if target.full_name in self.fail:
            raise self.fail[target.full_name]
        return list(self.docs.get(target.full_name, ()))
