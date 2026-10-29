"""주간 실행기 (SPEC FR-11.1·11.2·11.3·11.5) — 순서 · 이어 돌리기 · 예산 공유 · 실패 처리 · 실행 기록.

단계끼리는 import 하지 않는다(PLAN 1-2). 실제 단계는 CLI 가 `Step` 으로 묶어 넘기고,
여기서는 그 함수를 부르기만 한다.
종료 코드 규칙은 CLI 와 같다: 0 성공 · 3 예산으로 멈춤 · 그 밖은 실패.

- 산출물이 이미 있는 단계(`done`)는 건너뛴다 — 실패한 단계부터 다시 돌린다(FR-11.1).
- LLM 단계가 예산으로 멈추면 뒤의 LLM 단계는 건너뛰고, 비용 0 인 단계(export 등)는 그대로 돈다(FR-11.2).
- 핵심 단계(`critical`)가 실패하면 뒤 단계는 모두 막는다 — 계약 점검이 실패하면 아무것도 쓰지 않는다(FR-11.6).
"""

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from startrend.budget import BudgetExceeded
from startrend.core import io

STOPPED = 3


@dataclass(frozen=True)
class Step:
    name: str
    run: Callable[[], int]
    done: Callable[[], bool] | None = None   # 산출물이 이미 있으면 True — 건너뛴다
    llm: bool = False                         # 예산을 쓰는 단계
    critical: bool = True                     # 실패하면 뒤 단계를 막는다
    what: str = ""                            # dry-run 에 보이는 한 줄 설명


def run_weekly(steps: Sequence[Step], *, spent: Callable[[], float] = lambda: 0.0,
               log: Callable[[str], None] = print,
               clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    out: list[dict[str, Any]] = []
    blocked_by: str | None = None
    budget_out = False
    start_spent = spent()
    for step in steps:
        if blocked_by:
            out.append({"name": step.name, "status": "blocked", "reason": blocked_by})
            continue
        if step.llm and budget_out:
            out.append({"name": step.name, "status": "skipped", "reason": "budget"})
            log(f"[{step.name}] 건너뜀 — 예산이 바닥났다")
            continue
        if step.done and step.done():
            out.append({"name": step.name, "status": "skipped", "reason": "done"})
            log(f"[{step.name}] 건너뜀 — 이미 했다")
            continue
        log(f"[{step.name}] 시작")
        t0, s0 = clock(), spent()
        rec: dict[str, Any] = {"name": step.name}
        try:
            code = step.run()
            rec["status"] = "ok" if code == 0 else "stopped" if code == STOPPED else "failed"
            if code not in (0, STOPPED):
                rec["error"] = f"종료 코드 {code}"
        except BudgetExceeded as e:
            rec.update(status="stopped", error=str(e))
        except Exception as e:  # 단계 하나의 예외가 실행 기록까지 없애지 않게
            rec.update(status="failed", error=f"{type(e).__name__}: {e}")
        rec["seconds"] = round(clock() - t0, 1)
        rec["spent_usd"] = round(spent() - s0, 4)
        out.append(rec)
        log(f"[{step.name}] {rec['status']} · {rec['seconds']}초 · ${rec['spent_usd']}")
        if rec["status"] == "stopped":
            budget_out = True
        elif rec["status"] == "failed" and step.critical:
            blocked_by = step.name
    statuses = {s["status"] for s in out}
    status = "failed" if "failed" in statuses else "stopped" if budget_out else "ok"
    return {"status": status, "steps": out, "spent_usd": round(spent() - start_spent, 4)}


def plan_weekly(steps: Sequence[Step], *, estimates: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """dry-run — 단계를 부르지 않고(done 확인만) 무엇을 돌릴지와 단계별 추정을 모은다(FR-11.3)."""
    rows: list[dict[str, Any]] = []
    lo = hi = 0.0
    for step in steps:
        will = "skip" if step.done and step.done() else "run"
        row: dict[str, Any] = {"name": step.name, "what": step.what, "will": will, "llm": step.llm}
        est = estimates.get(step.name) or {}
        if will == "run":
            row.update(est)
            usd = est.get("usd")
            if usd:
                lo, hi = lo + float(usd[0]), hi + float(usd[1])
        rows.append(row)
    return {"steps": rows, "usd": [round(lo, 4), round(hi, 4)]}


def record_path(data_dir: Path, week: str) -> Path:
    return data_dir / "runs" / f"{week}.json"


def write_record(path: Path, week: str, result: Mapping[str, Any], *, started: str,
                 extra: Mapping[str, Any] | None = None) -> None:
    """실행 기록(FR-11.5). 같은 주를 다시 돌리면 앞 기록을 지우지 않고 뒤에 붙인다."""
    rec: dict[str, Any] = io.read_json(path) if path.exists() else {"week": week, "runs": []}
    rec["runs"].append({"started": started, **(extra or {}), **result})
    io.write_json(path, rec)
