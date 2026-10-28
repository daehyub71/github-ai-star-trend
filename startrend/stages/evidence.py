"""근거 수집 (SPEC FR-5.6·5.7·5.8). 비용 0 — 출처는 무료 API 와 무료 한도 검색만 쓴다.

출처를 정해진 순서(GitHub → HN → 웹 …)로 부르고 URL 로 중복을 없앤다. 앞 출처가 우선이다.
한 출처가 실패해도 멈추지 않고 실패를 기록한다 — 카드에 "수집 실패"로 남기기 위함이다(FR-5.7).
예산 초과만은 그대로 올려 보낸다(FR-11.2 — 근거 거르기가 LLM 을 쓰게 되면 해당).

목록은 `.work/<주>/evidence.jsonl`(저장소마다 한 줄), 원문은 `.work/<주>/raw/<해시>.txt`.
정본(data/)에는 URL·해시·짧은 인용만 간다(FR-5.8) — 그것은 analyze 가 카드에 남긴다.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from startrend.budget import BudgetExceeded
from startrend.clients.evidence.base import EvidenceSource, Target
from startrend.core import evidence as ev
from startrend.core import io, week

ERROR_CHARS = 300


@dataclass
class Collected:
    target: Target
    docs: list[ev.Evidence]
    failures: list[dict[str, str]] = field(default_factory=list)   # {"source", "error"}

    @property
    def failed_sources(self) -> list[str]:
        return [f["source"] for f in self.failures]

    @property
    def urls(self) -> list[str]:
        """인용 게이트에 넘길 근거 URL (FR-7.2)."""
        return [d.url for d in self.docs]


def gather(target: Target, sources: Sequence[EvidenceSource], *,
           log: Callable[[str], None] = print) -> Collected:
    docs: list[ev.Evidence] = []
    failures: list[dict[str, str]] = []
    for s in sources:
        try:
            got = s.collect(target)
        except BudgetExceeded:
            raise
        except Exception as e:          # FR-5.7 — 어떤 실패든 이 출처만 건너뛴다
            msg = f"{type(e).__name__}: {e}"[:ERROR_CHARS]
            failures.append({"source": s.name, "error": msg})
            log(f"  {target.full_name}: {s.name} 수집 실패 — {msg}")
            continue
        docs.extend(got)
    return Collected(target, ev.dedupe(docs), failures)


def week_dir(work_dir: Path, week_start: date) -> Path:
    return work_dir / week.week_name(week_start)


def evidence_path(work_dir: Path, week_start: date) -> Path:
    return week_dir(work_dir, week_start) / "evidence.jsonl"


def _row(c: Collected) -> dict[str, Any]:
    t = c.target
    return {"repo_id": t.repo_id, "full_name": t.full_name, "since": t.since.isoformat(),
            "until": t.until.isoformat(), "focus": [d.isoformat() for d in t.focus],
            "docs": [d.record() for d in c.docs], "failures": c.failures}


def write(work_dir: Path, week_start: date, collected: Sequence[Collected]) -> Path:
    """목록을 쓰고 원문을 해시 이름으로 남긴다(같은 해시는 다시 쓰지 않는다)."""
    raw = week_dir(work_dir, week_start) / "raw"
    for c in collected:
        for d in c.docs:
            p = raw / f"{d.content_hash}.txt"
            if d.text and not p.exists():
                io.write_text_atomic(p, d.text)
    path = evidence_path(work_dir, week_start)
    io.write_jsonl(path, [_row(c) for c in sorted(collected, key=lambda c: c.target.repo_id)])
    return path


def read(work_dir: Path, week_start: date) -> dict[int, Collected]:
    path = evidence_path(work_dir, week_start)
    out: dict[int, Collected] = {}
    if not path.exists():
        return out
    for row in io.read_jsonl(path):
        t = Target(int(row["repo_id"]), row["full_name"], since=date.fromisoformat(row["since"]),
                   until=date.fromisoformat(row["until"]),
                   focus=tuple(date.fromisoformat(x) for x in row.get("focus") or ()))
        docs = [ev.from_record(r) for r in row["docs"]]
        out[t.repo_id] = Collected(t, docs, list(row.get("failures") or []))
    return out
