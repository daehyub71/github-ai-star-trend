"""분류 평가 (SPEC FR-14.1·14.2·14.6·14.7, 결정 24·41). 이 파일 자체는 호출 0 · 비용 0.

정답 세트(`data/eval/goldset_*.jsonl`)와 판정 결과를 맞대어 채점한다.
- 필드별 정확도: **답한 것 중**(미분류·거절·누락 제외)과 **전체 기준**(그것들을 틀린 것으로)을 함께 낸다
- 카테고리: 정답이 AI 인 저장소만 — 정확도와 macro-F1(정답에 나온 카테고리마다 F1 의 평균)
- AI 여부: AI 를 양성으로 본 정밀도·재현율
- 보정 오차(ECE): 확신값을 주는 구현(JEV 등)만 — 확신 구간별 |실제 정확도 − 평균 확신| 의 가중 평균
- 1건당 비용·지연: 부른 쪽이 넘겨줄 때만
실행마다 `data/eval/runs/<날짜>-<이름>.json` + `.md` 를 남긴다 — 결정·문서의 수치는 이 리포트에서만 가져온다.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from startrend.clients.decision import MAX_TOKENS, TYPICAL_OUTPUT, input_token_range
from startrend.clients.llm import Usage, cost
from startrend.core import io
from startrend.core.taxonomy import Taxonomy

MODEL = "claude-opus-5-5"
ECE_BINS = 10
MAX_LISTED = 60          # 리포트에 적는 불일치 수


@dataclass(frozen=True)
class Label:
    repo_id: int
    full_name: str
    is_ai: bool
    type: str | None
    category: str | None     # 분류 체계 id. 비AI 면 None


def _bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if str(v).strip().lower() in ("yes", "true", "ai"):
        return True
    if str(v).strip().lower() in ("no", "false", "non-ai"):
        return False
    raise ValueError(f"is_ai 값을 알 수 없다: {v!r}")


def load_labels(path: Path, tax: Taxonomy, *, blind_only: bool = False) -> dict[int, Label]:
    """정답 라벨 — is_ai 는 true/false 또는 "yes"/"no", 카테고리는 id 나 이름(라벨링 화면).

    blind_only: 출처(source)가 "blind" 로 시작하는 행만 — 초안을 보지 않고 라벨한 것(FR-14.1 주 기준).
    """
    out: dict[int, Label] = {}
    for row in io.read_jsonl(path):
        if blind_only and not str(row.get("source", "")).startswith("blind"):
            continue
        is_ai = _bool(row["is_ai"])
        raw = row.get("category")
        cat = tax.resolve(raw) if raw not in (None, "", "none") else None
        if raw not in (None, "", "none") and cat is None:
            raise ValueError(f"{row.get('full_name')}: 분류 체계에 없는 카테고리 {raw!r}")
        out[int(row["repo_id"])] = Label(int(row["repo_id"]), str(row.get("full_name", "")), is_ai,
                                         row.get("type"), cat if is_ai else None)
    return out


def load_predictions(path: Path) -> dict[int, dict[str, Any]]:
    return {int(r["repo_id"]): r for r in io.read_jsonl(path)}


def _ratio(a: int, b: int) -> float | None:
    return a / b if b else None


def _f1(p: float | None, r: float | None) -> float:
    return 2 * p * r / (p + r) if p and r else 0.0


def score(gold: Mapping[int, Label], pred: Mapping[int, Mapping[str, Any]], *,
          cost_usd: float | None = None, seconds: float | None = None) -> dict[str, Any]:
    ids = sorted(gold)
    n = len(ids)
    ok = [i for i in ids if i in pred and pred[i].get("status") == "ok"]
    unanswered = {"unclassified": 0, "refused": 0, "missing": 0}
    disagreements: list[dict[str, Any]] = []
    for i in ids:
        if i not in pred:
            unanswered["missing"] += 1
            disagreements.append({"repo_id": i, "full_name": gold[i].full_name, "field": "status",
                                  "gold": "-", "pred": "missing"})
        elif pred[i].get("status") != "ok":
            s = str(pred[i].get("status"))
            unanswered[s if s in unanswered else "unclassified"] += 1
            disagreements.append({"repo_id": i, "full_name": gold[i].full_name, "field": "status",
                                  "gold": "-", "pred": s})
    unanswered = {k: v for k, v in unanswered.items() if v}

    ai_ok = [i for i in ok if pred[i].get("is_ai") == gold[i].is_ai]
    tp = sum(1 for i in ok if gold[i].is_ai and pred[i].get("is_ai") is True)
    fp = sum(1 for i in ok if not gold[i].is_ai and pred[i].get("is_ai") is True)
    fn = sum(1 for i in ok if gold[i].is_ai and pred[i].get("is_ai") is not True)
    typed = [i for i in ok if gold[i].type]
    type_ok = [i for i in typed if pred[i].get("type") == gold[i].type]

    cat_items = [i for i in ok if gold[i].is_ai]
    pcat = {i: (pred[i].get("category") if pred[i].get("is_ai") else None) for i in cat_items}
    classes = sorted({str(gold[i].category) for i in cat_items if gold[i].category is not None})
    per_class: dict[str, dict[str, Any]] = {}
    for c in classes:
        c_tp = sum(1 for i in cat_items if gold[i].category == c and pcat[i] == c)
        c_fp = sum(1 for i in cat_items if gold[i].category != c and pcat[i] == c)
        c_fn = sum(1 for i in cat_items if gold[i].category == c and pcat[i] != c)
        p, r = _ratio(c_tp, c_tp + c_fp), _ratio(c_tp, c_tp + c_fn)
        per_class[c] = {"support": c_tp + c_fn, "precision": p, "recall": r, "f1": _f1(p, r)}
    cat_ok = [i for i in cat_items if pcat[i] == gold[i].category]
    macro_f1 = sum(v["f1"] for v in per_class.values()) / len(per_class) if per_class else None

    for i in ok:
        for field, g, p in (("is_ai", gold[i].is_ai, pred[i].get("is_ai")),
                            ("type", gold[i].type, pred[i].get("type")),
                            ("category", gold[i].category, pcat.get(i, pred[i].get("category")))):
            if field == "type" and not g:
                continue
            if field == "category" and not gold[i].is_ai:
                continue
            if g != p:
                disagreements.append({"repo_id": i, "full_name": gold[i].full_name, "field": field,
                                      "gold": g, "pred": p})

    return {
        "n": n, "answered": len(ok), "unanswered": unanswered,
        "is_ai": {"accuracy": _ratio(len(ai_ok), len(ok)), "accuracy_strict": _ratio(len(ai_ok), n),
                  "precision": _ratio(tp, tp + fp), "recall": _ratio(tp, tp + fn)},
        "type": {"accuracy": _ratio(len(type_ok), len(typed)), "n": len(typed)},
        "category": {"accuracy": _ratio(len(cat_ok), len(cat_items)), "n": len(cat_items),
                     "macro_f1": macro_f1, "per_class": per_class},
        "calibration_error": _ece(gold, pred, ok),
        "cost_per_item_usd": cost_usd / n if cost_usd is not None and n else None,
        "seconds_per_item": seconds / n if seconds is not None and n else None,
        "disagreements": disagreements,
    }


def _ece(gold: Mapping[int, Label], pred: Mapping[int, Mapping[str, Any]], ok: Sequence[int]) -> float | None:
    """AI 여부 판정의 확신값 보정 오차. 확신값이 하나도 없으면 None."""
    rows = [(float(pred[i]["confidence"]), pred[i].get("is_ai") == gold[i].is_ai)
            for i in ok if pred[i].get("confidence") is not None]
    if not rows:
        return None
    total = 0.0
    for b in range(ECE_BINS):
        lo, hi = b / ECE_BINS, (b + 1) / ECE_BINS
        inbin = [(c, hit) for c, hit in rows if lo <= c < hi or (b == ECE_BINS - 1 and c == 1.0)]
        if inbin:
            acc = sum(hit for _, hit in inbin) / len(inbin)
            conf = sum(c for c, _ in inbin) / len(inbin)
            total += len(inbin) / len(rows) * abs(acc - conf)
    return total


def _pct(v: float | None) -> str:
    return "-" if v is None else f"{v * 100:.1f}%"


def report_md(r: Mapping[str, Any], *, title: str, tax: Taxonomy, notes: Sequence[str] = ()) -> str:
    def cname(c: Any) -> str:
        return tax.name_of(str(c)) if c else "(없음)"

    lines = [f"# {title}", ""]
    lines += [f"- {n}" for n in notes]
    lines += ["", f"정답 {r['n']}개 · 답함 {r['answered']}개" +
              (f" · 못 답함 {r['unanswered']}" if r["unanswered"] else ""), "",
              "| 지표 | 답한 것 중 | 전체 기준 |", "|---|---:|---:|",
              f"| AI 여부 정확도 | {_pct(r['is_ai']['accuracy'])} | {_pct(r['is_ai']['accuracy_strict'])} |",
              f"| AI 정밀도 · 재현율 | {_pct(r['is_ai']['precision'])} · {_pct(r['is_ai']['recall'])} | |",
              f"| 유형 정확도 ({r['type']['n']}개) | {_pct(r['type']['accuracy'])} | |",
              f"| 카테고리 정확도 (정답 AI {r['category']['n']}개) | {_pct(r['category']['accuracy'])} | |",
              f"| 카테고리 macro-F1 | {_pct(r['category']['macro_f1'])} | |",
              f"| 보정 오차(ECE) | {_pct(r['calibration_error'])} | |"]
    if r.get("cost_per_item_usd") is not None:
        lines.append(f"| 1건당 비용 | ${r['cost_per_item_usd']:.4f} | |")
    if r.get("seconds_per_item") is not None:
        lines.append(f"| 1건당 시간 | {r['seconds_per_item']:.1f}초 | |")
    if r["category"]["per_class"]:
        lines += ["", "## 카테고리별", "", "| 카테고리 | 정답 수 | 정밀도 | 재현율 | F1 |",
                  "|---|---:|---:|---:|---:|"]
        for c, v in sorted(r["category"]["per_class"].items(), key=lambda kv: -kv[1]["support"]):
            lines.append(f"| {cname(c)} | {v['support']} | {_pct(v['precision'])} | {_pct(v['recall'])} | "
                         f"{_pct(v['f1'])} |")
    if r["disagreements"]:
        lines += ["", f"## 불일치 ({len(r['disagreements'])}건)", "", "| 저장소 | 항목 | 정답 | 판정 |",
                  "|---|---|---|---|"]
        for d in r["disagreements"][:MAX_LISTED]:
            g, p = d["gold"], d["pred"]
            if d["field"] == "category":
                g, p = cname(g), cname(p)
            lines.append(f"| {d['full_name']} | {d['field']} | {g} | {p} |")
        if len(r["disagreements"]) > MAX_LISTED:
            lines.append(f"| … {len(r['disagreements']) - MAX_LISTED}건 더 (json 에 전부) | | | |")
    return "\n".join(lines) + "\n"


def write_run(data_dir: Path, name: str, result: Mapping[str, Any], md: str, *,
              today: date | None = None) -> Path:
    """`data/eval/runs/<날짜>-<이름>[-n].json` + `.md`. 이전 실행은 덮어쓰지 않는다(기록이다)."""
    runs = data_dir / "eval" / "runs"
    stem = f"{(today or date.today()).isoformat()}-{name}"
    path, k = runs / f"{stem}.json", 2
    while path.exists():
        path, k = runs / f"{stem}-{k}.json", k + 1
    io.write_json(path, dict(result))
    io.write_text_atomic(path.with_suffix(".md"), md)
    return path


def dry_run(*, n_items: int, system_prompt: str, batch: bool = True) -> dict[str, Any]:
    """정답 세트를 판정기로 한 번 돌릴 때의 호출 수·입력 토큰·비용 범위. 호출 0회 (FR-14.7)."""
    tokens_in = input_token_range(system_prompt)       # (보통, 보수적) — 하한·상한에 각각 (P2-15)
    lo = cost(MODEL, Usage(tokens_in[0], TYPICAL_OUTPUT), batch=batch)
    hi = cost(MODEL, Usage(tokens_in[1], MAX_TOKENS), batch=batch)
    return {"calls": n_items, "input_tokens_per_item": tokens_in, "batch": batch,
            "usd": (n_items * lo, n_items * hi), "usd_retry_upper": 2 * n_items * hi,
            "assumptions": {"output_tokens": (TYPICAL_OUTPUT, MAX_TOKENS), "model": MODEL}}
