"""stages.evaluate — 분류 정답 세트로 판정을 채점한다 (FR-14.1·14.2·14.6·14.7). 호출 0, 비용 0."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from startrend.core import io
from startrend.core import taxonomy as tx
from startrend.stages import evaluate as ev

ROOT = Path(__file__).resolve().parents[1]
TAX = tx.load(ROOT / "data" / "taxonomy.toml")
TOOL = "도구/라이브러리"


def lab(rid: int, is_ai: bool, cat: str | None = None, typ: str = TOOL) -> ev.Label:
    return ev.Label(rid, f"o/r{rid}", is_ai, typ, cat)


def pred(is_ai: bool | None, cat: str | None = None, typ: str = TOOL, status: str = "ok",
         confidence: float | None = None) -> dict[str, Any]:
    return {"status": status, "is_ai": is_ai, "type": typ, "category": cat, "confidence": confidence}


# --- 정답 라벨 읽기 ---


def test_evaluate_load_labels_normalizes_yes_no_and_category_names(tmp_path):
    p = tmp_path / "gold.jsonl"
    io.write_jsonl(p, [
        {"repo_id": 1, "full_name": "o/a", "is_ai": "yes", "type": TOOL, "category": "MCP 서버·도구"},
        {"repo_id": 2, "full_name": "o/b", "is_ai": "no", "type": "교육자료", "category": None},
        {"repo_id": 3, "full_name": "o/c", "is_ai": True, "type": "기타", "category": "rag"},
    ])
    gold = ev.load_labels(p, TAX)
    assert gold[1] == ev.Label(1, "o/a", True, "도구/라이브러리", "mcp-tools")
    assert gold[2].is_ai is False and gold[2].category is None
    assert gold[3].category == "rag"


def test_evaluate_load_labels_rejects_unknown_category(tmp_path):
    p = tmp_path / "gold.jsonl"
    io.write_jsonl(p, [{"repo_id": 1, "full_name": "o/a", "is_ai": "yes", "type": "기타",
                        "category": "양자 AI"}])
    with pytest.raises(ValueError, match="양자 AI"):
        ev.load_labels(p, TAX)


def test_evaluate_load_labels_on_the_real_blind_set():
    gold = ev.load_labels(ROOT / "data" / "eval" / "goldset_blind_labels.jsonl", TAX)
    assert len(gold) == 30 and sum(g.is_ai for g in gold.values()) == 19


# --- 채점 ---


def test_evaluate_score_perfect():
    gold = {1: lab(1, True, "rag"), 2: lab(2, False)}
    r = ev.score(gold, {1: pred(True, "rag"), 2: pred(False)})
    assert r["n"] == 2 and r["answered"] == 2
    assert r["is_ai"]["accuracy"] == 1.0 and r["type"]["accuracy"] == 1.0
    assert r["category"]["accuracy"] == 1.0 and r["category"]["macro_f1"] == 1.0
    assert r["disagreements"] == []


def test_evaluate_score_separates_answered_and_strict_accuracy():
    # 미분류·누락은 "답한 것 중 정확도"에서는 빠지고, "전체 기준"에서는 틀린 것으로 센다
    gold = {1: lab(1, True, "rag"), 2: lab(2, False), 3: lab(3, False), 4: lab(4, True, "rag")}
    preds = {1: pred(True, "rag"), 2: pred(True, "rag"), 3: pred(None, status="unclassified")}
    r = ev.score(gold, preds)
    assert r["answered"] == 2 and r["unanswered"] == {"unclassified": 1, "missing": 1}
    assert r["is_ai"]["accuracy"] == pytest.approx(1 / 2)
    assert r["is_ai"]["accuracy_strict"] == pytest.approx(1 / 4)
    kinds = {(d["repo_id"], d["field"]) for d in r["disagreements"]}
    assert kinds == {(2, "is_ai"), (3, "status"), (4, "status")}


def test_evaluate_score_category_macro_f1():
    # 정답 AI 3개: x, x, y — 판정 x, y, y
    # x: P 1 · R 0.5 · F1 0.667 / y: P 0.5 · R 1 · F1 0.667 → macro 0.667, 정확도 2/3
    gold = {1: lab(1, True, "rag"), 2: lab(2, True, "rag"), 3: lab(3, True, "mcp-tools")}
    r = ev.score(gold, {1: pred(True, "rag"), 2: pred(True, "mcp-tools"), 3: pred(True, "mcp-tools")})
    assert r["category"]["accuracy"] == pytest.approx(2 / 3)
    assert r["category"]["macro_f1"] == pytest.approx(2 / 3, abs=1e-3)
    per = r["category"]["per_class"]
    assert per["rag"]["support"] == 2 and per["rag"]["recall"] == pytest.approx(0.5)


def test_evaluate_score_category_counts_non_ai_answer_as_wrong():
    gold = {1: lab(1, True, "rag")}
    r = ev.score(gold, {1: pred(False)})
    assert r["category"]["accuracy"] == 0.0 and r["category"]["n"] == 1


def test_evaluate_score_ai_precision_and_recall():
    gold = {1: lab(1, True, "rag"), 2: lab(2, True, "rag"), 3: lab(3, False), 4: lab(4, False)}
    r = ev.score(gold, {1: pred(True, "rag"), 2: pred(False), 3: pred(True, "rag"), 4: pred(False)})
    assert r["is_ai"]["precision"] == pytest.approx(0.5) and r["is_ai"]["recall"] == pytest.approx(0.5)


def test_evaluate_calibration_only_when_confidence_is_given():
    gold = {i: lab(i, True, "rag") for i in range(1, 5)}
    assert ev.score(gold, {i: pred(True, "rag") for i in gold})["calibration_error"] is None
    # 확신 0.9 로 4개 중 3개 맞힘 → |0.75 - 0.9| = 0.15
    preds = {1: pred(True, "rag", confidence=0.9), 2: pred(True, "rag", confidence=0.9),
             3: pred(True, "rag", confidence=0.9), 4: pred(False, confidence=0.9)}
    assert ev.score(gold, preds)["calibration_error"] == pytest.approx(0.15)


def test_evaluate_score_per_item_cost_and_latency():
    gold = {1: lab(1, False), 2: lab(2, False)}
    r = ev.score(gold, {1: pred(False), 2: pred(False)}, cost_usd=0.02, seconds=10.0)
    assert r["cost_per_item_usd"] == pytest.approx(0.01) and r["seconds_per_item"] == pytest.approx(5.0)
    assert ev.score(gold, {1: pred(False)})["cost_per_item_usd"] is None


# --- 리포트·기록 ---


def test_evaluate_report_lists_metrics_and_disagreements():
    gold = {1: lab(1, True, "rag"), 2: lab(2, False)}
    r = ev.score(gold, {1: pred(True, "mcp-tools"), 2: pred(False)})
    md = ev.report_md(r, title="블라인드 30 대 Claude 초안", notes=["정답: 사용자"], tax=TAX)
    assert md.startswith("# 블라인드 30 대 Claude 초안")
    assert "macro-F1" in md and "o/r1" in md and "RAG·검색" in md and "정답: 사용자" in md


def test_evaluate_write_run_never_overwrites(tmp_path):
    d = date(2026, 10, 27)
    a = ev.write_run(tmp_path, "blind30", {"x": 1}, "# a", today=d)
    b = ev.write_run(tmp_path, "blind30", {"x": 2}, "# b", today=d)
    assert a != b and a.parent == tmp_path / "eval" / "runs"
    assert json.loads(a.read_text(encoding="utf-8"))["x"] == 1
    assert a.with_suffix(".md").read_text(encoding="utf-8") == "# a"
    assert json.loads(b.read_text(encoding="utf-8"))["x"] == 2


# --- dry-run (FR-14.7) ---


def test_evaluate_dry_run_prices_without_calls():
    est = ev.dry_run(n_items=200, system_prompt="s" * 3000, batch=True)
    assert est["calls"] == 200 and est["input_tokens_per_item"] > 1000
    lo, hi = est["usd"]
    assert 0 < lo < hi
    assert est["usd_retry_upper"] == pytest.approx(2 * hi)    # 전부 한 번씩 다시 묻는 최악
