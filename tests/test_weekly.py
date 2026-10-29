"""stages.weekly — 주간 실행기 (FR-11.1·11.2·11.3·11.5).

단계는 CLI 가 넘겨 주는 함수다(단계끼리 import 금지 — PLAN 1-2). 실행기는 순서·이어 돌리기·예산 공유·
실패 처리·실행 기록만 맡는다. 종료 코드 규칙은 CLI 와 같다: 0 성공 · 3 예산으로 멈춤 · 그 밖은 실패.
"""

from collections.abc import Callable
from pathlib import Path

from startrend.budget import BudgetExceeded
from startrend.core import io
from startrend.stages import weekly
from startrend.stages.weekly import Step


class Calls:
    def __init__(self) -> None:
        self.order: list[str] = []
        self.spent = 0.0

    def step(self, name: str, code: int = 0, cost: float = 0.0, **kw: object) -> Step:
        def run() -> int:
            self.order.append(name)
            self.spent += cost
            return code
        return Step(name=name, run=run, **kw)  # type: ignore[arg-type]


def _ticks() -> Callable[[], float]:
    t = iter(range(0, 1000, 2))
    return lambda: float(next(t))


def _run(steps: list[Step], c: Calls) -> dict[str, object]:
    return weekly.run_weekly(steps, spent=lambda: c.spent, log=lambda m: None, clock=_ticks())


def test_weekly_runs_steps_in_order_and_records_time_and_cost():
    c = Calls()
    out = _run([c.step("discover"), c.step("classify", cost=1.25, llm=True), c.step("export")], c)
    assert c.order == ["discover", "classify", "export"]
    assert out["status"] == "ok" and out["spent_usd"] == 1.25
    steps = out["steps"]
    assert isinstance(steps, list)
    assert [s["status"] for s in steps] == ["ok", "ok", "ok"]
    assert steps[1]["spent_usd"] == 1.25 and steps[1]["seconds"] == 2.0


def test_weekly_skips_steps_already_done():
    # 실패한 단계부터 다시 돌릴 수 있다(FR-11.1) — 산출물이 있는 단계는 건너뛴다
    c = Calls()
    out = _run([c.step("discover", done=lambda: True), c.step("stars")], c)
    assert c.order == ["stars"]
    steps = out["steps"]
    assert isinstance(steps, list)
    assert steps[0] == {"name": "discover", "status": "skipped", "reason": "done"}


def test_weekly_budget_stop_skips_later_llm_steps_but_keeps_free_ones():
    # FR-11.2 — 예산을 넘으면 LLM 단계만 멈추고, 비용 0 인 결과는 그대로 낸다
    c = Calls()
    out = _run([c.step("classify", llm=True), c.step("analyze", code=3, llm=True),
                c.step("brief", llm=True), c.step("export")], c)
    assert c.order == ["classify", "analyze", "export"]
    steps = out["steps"]
    assert isinstance(steps, list)
    assert [s["status"] for s in steps] == ["ok", "stopped", "skipped", "ok"]
    assert steps[2]["reason"] == "budget"
    assert out["status"] == "stopped"


def test_weekly_budget_exception_counts_as_stopped():
    def boom() -> int:
        raise BudgetExceeded("남은 예산 $0.01")
    c = Calls()
    out = _run([Step("brief", boom, llm=True), c.step("export")], c)
    steps = out["steps"]
    assert isinstance(steps, list)
    assert steps[0]["status"] == "stopped" and "남은 예산" in steps[0]["error"]
    assert c.order == ["export"]


def test_weekly_critical_failure_blocks_the_rest():
    c = Calls()
    out = _run([c.step("contract", code=1), c.step("discover"), c.step("export")], c)
    assert c.order == ["contract"]
    steps = out["steps"]
    assert isinstance(steps, list)
    assert [s["status"] for s in steps] == ["failed", "blocked", "blocked"]
    assert out["status"] == "failed"


def test_weekly_non_critical_failure_is_recorded_and_the_run_goes_on():
    def broken() -> int:
        raise RuntimeError("Tavily 응답 없음")
    c = Calls()
    out = _run([Step("evidence", broken, critical=False), c.step("export")], c)
    steps = out["steps"]
    assert isinstance(steps, list)
    assert steps[0]["status"] == "failed" and "Tavily" in steps[0]["error"]
    assert c.order == ["export"] and out["status"] == "failed"


def test_weekly_plan_shows_what_would_run_without_calling_anything():
    # FR-11.3 — dry-run 은 단계를 부르지 않는다
    c = Calls()
    steps = [c.step("discover", done=lambda: True, what="스냅샷"), c.step("classify", llm=True, what="판정")]
    plan = weekly.plan_weekly(steps, estimates={"classify": {"usd": [0.4, 1.2], "llm_calls": 20}})
    assert c.order == []
    assert plan["steps"] == [
        {"name": "discover", "what": "스냅샷", "will": "skip", "llm": False},
        {"name": "classify", "what": "판정", "will": "run", "llm": True, "usd": [0.4, 1.2], "llm_calls": 20},
    ]
    assert plan["usd"] == [0.4, 1.2]


def test_weekly_record_keeps_every_run_of_the_same_week(tmp_path: Path):
    # FR-11.5 — 실행 기록. 같은 주를 이어 돌리면 앞 기록 뒤에 붙인다
    path = weekly.record_path(tmp_path, "2026-10-25")
    assert path == tmp_path / "runs" / "2026-10-25.json"
    weekly.write_record(path, "2026-10-25", {"status": "failed", "steps": []}, started="2026-11-02T00:00:00Z")
    weekly.write_record(path, "2026-10-25", {"status": "ok", "steps": []}, started="2026-11-02T03:00:00Z")
    rec = io.read_json(path)
    assert rec["week"] == "2026-10-25"
    assert [r["status"] for r in rec["runs"]] == ["failed", "ok"]
    assert rec["runs"][1]["started"] == "2026-11-02T03:00:00Z"
