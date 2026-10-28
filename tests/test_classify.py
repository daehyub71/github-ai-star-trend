"""stages.classify — 랭킹 후보만, 축마다 AI 15개까지, 입력 해시 증분, 예산·dry-run.

FR-3.1·3.5·3.6, 결정 30.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from startrend.budget import BudgetExceeded
from startrend.clients import decision as dc
from startrend.clients import llm
from startrend.clients.github_mock import MockGitHub
from startrend.core import io, meta, weekfile
from startrend.core import taxonomy as tx
from startrend.core.weekfile import WeekRow
from startrend.stages import classify as cl
from tests import synth

W = date(2026, 10, 18)
OLD = date(2020, 1, 1)
TAX = tx.load(Path(__file__).resolve().parents[1] / "data" / "taxonomy.toml")


# --- 다음에 판정할 묶음 ---


def test_classify_next_round_walks_until_enough_ai():
    pool = {"w/gain": [1, 2, 3, 4, 5, 6, 7, 8]}
    # 아무것도 모를 때: 3개가 필요하고 비율 0.5 → 미판정 6개
    assert cl.next_round(pool, {}, need=3, ratio=0.5) == [1, 2, 3, 4, 5, 6]
    # 1·2 는 AI, 3 은 비AI, 4 는 미분류 → AI 2개 · 1개 더 필요 → 미판정 2개(5, 6)
    known: dict[int, bool | None] = {1: True, 2: True, 3: False, 4: None}
    assert cl.next_round(pool, known, need=3, ratio=0.5) == [5, 6]
    # 3개가 찼으면 끝
    assert cl.next_round(pool, {1: True, 2: True, 3: True}, need=3, ratio=0.5) == []


def test_classify_next_round_stops_when_pool_is_exhausted():
    assert cl.next_round({"w/gain": [1, 2]}, {1: False, 2: False}, need=15) == []


def test_classify_next_round_merges_axes_without_duplicates():
    pool = {"w/gain": [1, 2, 3], "w/total": [3, 9, 1]}
    assert cl.next_round(pool, {}, need=1, ratio=0.5) == [1, 2, 3, 9]


# --- 실행 ---


def _setup(tmp_path, n: int = 12) -> MockGitHub:
    rows = [WeekRow(i, f"o/r{i}", OLD, 5000 + i, 100 + i, False, None) for i in range(1, n + 1)]
    weekfile.write(weekfile.week_path(tmp_path, W), rows)
    order = list(range(n, 0, -1))          # 증가 큰 순
    io.write_json(tmp_path / "weekly" / "2026-10-18" / "rankings.json",
                  {"week": "2026-10-18", "pool": {"gain": order, "total": order}})
    gh = MockGitHub()
    for r in rows:
        gh.add_repo(synth.repo(r.full_name, id=r.id, stars=r.stars_end, description=f"repo {r.id}"))
        gh.add_readme(r.full_name, f"# r{r.id}")
    return gh


def _table(ids) -> dict[int, dc.Decision]:
    # 짝수는 AI, 홀수는 비AI
    return {i: (dc.Decision(status="ok", is_ai=True, type="도구/라이브러리", category="rag") if i % 2 == 0
                else dc.Decision(status="ok", is_ai=False, type="교육자료")) for i in ids}


def test_classify_run_decides_only_what_the_ai_tab_needs(tmp_path):
    gh = _setup(tmp_path)
    decider = dc.MockDecider(_table(range(1, 13)))
    stats = cl.run_classify(gh, decider, data_dir=tmp_path, weeks=[W], need=3, ratio=0.5, log=lambda m: None)
    # 12 → 11 → … 위에서부터. AI(짝수) 3개 = 12, 10, 8 → 그 아래(7 이하)는 판정하지 않는다
    assert sorted(decider.asked) == [7, 8, 9, 10, 11, 12]
    assert stats["decided"] == 6 and stats["reused"] == 0 and stats["stopped"] is None
    m = meta.load(tmp_path, 12)
    assert m is not None and m["classify"]["is_ai"] is True and m["classify"]["category"] == "rag"
    assert m["classify"]["input_hash"] and m["classify"]["fingerprint"] == "mock"


def test_classify_run_reuses_decisions_when_input_is_unchanged(tmp_path):
    gh = _setup(tmp_path)
    cl.run_classify(gh, dc.MockDecider(_table(range(1, 13))), data_dir=tmp_path, weeks=[W], need=3, ratio=0.5,
                    log=lambda m: None)
    again = dc.MockDecider(_table(range(1, 13)))
    stats = cl.run_classify(gh, again, data_dir=tmp_path, weeks=[W], need=3, ratio=0.5, log=lambda m: None)
    assert again.asked == [] and stats["reused"] == 6
    gh.add_readme("o/r12", "# r12 — rewritten")          # 입력이 바뀌면 그것만 다시
    third = dc.MockDecider(_table(range(1, 13)))
    cl.run_classify(gh, third, data_dir=tmp_path, weeks=[W], need=3, ratio=0.5, log=lambda m: None)
    assert third.asked == [12]


def test_classify_run_stops_on_budget_and_keeps_progress(tmp_path):
    gh = _setup(tmp_path)

    class Capped(dc.MockDecider):
        def classify(self, item):
            if len(self.asked) >= 2:
                raise BudgetExceeded("cap")
            return super().classify(item)

    stats = cl.run_classify(gh, Capped(_table(range(1, 13))), data_dir=tmp_path, weeks=[W], need=3, ratio=0.5,
                            log=lambda m: None)
    assert stats["stopped"] == "budget" and stats["decided"] == 2
    assert meta.load(tmp_path, 12) is not None and meta.load(tmp_path, 11) is not None


def test_classify_run_sends_each_round_as_one_batch(tmp_path):
    # FR-3.7 — 판정 후보를 묶음마다 모아 Batch 한 번으로 보낸다.
    # 상태 파일 이름이 겹치지 않게 묶음 번호를 붙인다
    gh = _setup(tmp_path)
    calls: list[tuple[str, list[str]]] = []

    def runner(reqs: dict[str, llm.LLMRequest], tag: str) -> dict[str, llm.BatchItem]:
        calls.append((tag, sorted(reqs)))
        out = {}
        for cid in reqs:
            rid = int(cid[1:].split("-")[0])
            body = ({"is_ai": True, "type": "도구/라이브러리", "category": "rag"} if rid % 2 == 0
                    else {"is_ai": False, "type": "교육자료", "category": "none"})
            text = json.dumps({**body, "secondary": "none", "reason": "x"}, ensure_ascii=False)
            resp = llm.LLMResponse(text, "end_turn", llm.Usage(1000, 50), "claude-opus-5-5")
            out[cid] = llm.BatchItem(resp)
        return out

    decider = dc.LLMDecider(llm.MockLLM([]), TAX)        # 일반 호출은 없어야 한다
    stats = cl.run_classify(gh, decider, data_dir=tmp_path, weeks=[W], need=3, ratio=0.5, batch=runner,
                            log=lambda m: None)
    assert calls == [("1-1", sorted(f"r{i}-1" for i in range(7, 13)))]
    assert stats["decided"] == 6 and stats["rounds"] == 1
    m = meta.load(tmp_path, 12)
    assert m is not None and m["classify"]["category"] == "rag"
    assert m["classify"]["fingerprint"] == decider.fingerprint


def _answering_runner(calls: list[tuple[str, int]], fail_on: int | None = None):
    """짝수 ID 는 AI(rag), 홀수는 비AI 로 답하는 가짜 Batch. fail_on 번째 호출에서 예산 초과."""
    def runner(reqs: dict[str, llm.LLMRequest], tag: str) -> dict[str, llm.BatchItem]:
        calls.append((tag, len(reqs)))
        if fail_on is not None and len(calls) == fail_on:
            raise BudgetExceeded("cap")
        out = {}
        for cid in reqs:
            rid = int(cid[1:].split("-")[0])
            body = ({"is_ai": True, "type": "도구/라이브러리", "category": "rag"} if rid % 2 == 0
                    else {"is_ai": False, "type": "교육자료", "category": "none"})
            text = json.dumps({**body, "secondary": "none", "reason": "x"}, ensure_ascii=False)
            resp = llm.LLMResponse(text, "end_turn", llm.Usage(1000, 50), "claude-opus-5-5")
            out[cid] = llm.BatchItem(resp)
        return out
    return runner


def test_classify_run_splits_a_round_into_chunks(tmp_path):
    # 묶음 전체의 최악 비용이 상한을 넘어 통째로 막히지 않게, 조각으로 나눠 차례로 보낸다(P2-9)
    gh = _setup(tmp_path)
    calls: list[tuple[str, int]] = []
    decider = dc.LLMDecider(llm.MockLLM([]), TAX)
    stats = cl.run_classify(gh, decider, data_dir=tmp_path, weeks=[W], need=3, ratio=0.5,
                            batch=_answering_runner(calls), chunk=4, log=lambda m: None)
    assert calls == [("1-c1-1", 4), ("1-c2-1", 2)] and stats["decided"] == 6


def test_classify_run_keeps_earlier_chunks_when_a_later_one_hits_the_budget(tmp_path):
    gh = _setup(tmp_path)
    calls: list[tuple[str, int]] = []
    decider = dc.LLMDecider(llm.MockLLM([]), TAX)
    stats = cl.run_classify(gh, decider, data_dir=tmp_path, weeks=[W], need=3, ratio=0.5,
                            batch=_answering_runner(calls, fail_on=2), chunk=4, log=lambda m: None)
    assert stats["stopped"] == "budget" and stats["decided"] == 4
    assert sum(1 for i in range(7, 13) if (meta.load(tmp_path, i) or {}).get("classify")) == 4


def test_classify_unclassified_is_not_retried_and_does_not_count_as_ai(tmp_path):
    gh = _setup(tmp_path, n=4)
    table = {4: dc.Decision(status="unclassified", error="x"), 3: dc.Decision(status="refused"),
             2: dc.Decision(status="ok", is_ai=True, type="기타", category="other-ai"),
             1: dc.Decision(status="ok", is_ai=True, type="기타", category="other-ai")}
    stats = cl.run_classify(gh, dc.MockDecider(table), data_dir=tmp_path, weeks=[W], need=2, ratio=1.0,
                            log=lambda m: None)
    assert stats["unclassified"] == ["o/r4", "o/r3"] and stats["decided"] == 4


def test_classify_input_hash_follows_fingerprint_and_readme():
    a = dc.RepoInput(1, "o/r", "d", ("t",), "Py", "# readme")
    assert cl.input_hash(a, "p1") == cl.input_hash(a, "p1")
    assert cl.input_hash(a, "p1") != cl.input_hash(a, "p2")
    b = dc.RepoInput(1, "o/r", "d", ("t",), "Py", "# readme changed")
    assert cl.input_hash(a, "p1") != cl.input_hash(b, "p1")


# --- dry-run ---


def test_classify_dry_run_makes_no_calls_and_prices_a_range(tmp_path):
    gh = _setup(tmp_path)
    est = cl.dry_run(data_dir=tmp_path, weeks=[W], system_prompt="s" * 3000, need=3, ratio=0.5, batch=True)
    assert gh.stats.calls == {} or sum(gh.stats.calls.values()) == 0
    assert est["first_round"] == 6 and est["upper_bound"] == 12
    lo, hi = est["per_item_usd"]
    assert 0 < lo < hi
    assert est["first_round_usd"] == pytest.approx((6 * lo, 6 * hi))
    assert est["github_calls_first_round"] == 12   # 저장소 정보 + README
