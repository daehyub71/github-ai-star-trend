"""D-7 실측 — Claude 웹 검색으로 저장소 근거를 모을 때 실제 토큰·비용 (SPEC 부록 C-1).

기본은 dry-run: 보낼 요청과 비용 추정만 보여 주고 호출하지 않는다(워크스페이스 원칙 3).
--run 일 때만 호출한다. 누적 비용이 --budget 을 넘으면 거기서 멈춘다.

    .\\.venv\\Scripts\\python.exe scripts\\measure_web_search.py            # dry-run
    .\\.venv\\Scripts\\python.exe scripts\\measure_web_search.py --run      # 과금

키는 환경변수 STARTREND_ANTHROPIC_API_KEY (NFR-8) — 출력·기록하지 않는다.
결과: .work/measure/web_search-<날짜>.json
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MODEL = "claude-opus-5-5"  # 결정 26
# 100만 토큰당 달러 (2026-09-25 공식 표, MEASURE §9) · 검색은 1회당
PRICE = {"input": 4.0, "output": 20.0, "cache_read": 0.20, "cache_write": 5.0, "search": 0.01}
TOOLS = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 3},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 3, "max_content_tokens": 8000},
]
MAX_TOKENS = 8000
REPOS = ["cloudflare/security-audit-skill", "Graphify-Labs/graphify", "debpalash/VoiceStudio",
         "stablyai/orca", "google-research/harness2"]
# dry-run 추정의 가정 (저장소 1개) — 이 실측으로 바꿀 값이다
ASSUME = {"input": (10_000, 60_000), "output": (2_000, 8_000), "searches": (2, 3)}

PROMPT = """You are collecting evidence of real-world use for one GitHub repository.

Repository: {name} (https://github.com/{name})
Description: {desc}

Search the web for pages ABOUT this repository that are not the repository itself: blog posts,
tutorials, user reviews or experience reports, comparisons, and news. Skip pages that only mirror
the README, and skip other repositories with a similar name.

Return only a JSON array (no prose) of up to 8 sources:
[{{"url": "...", "title": "...", "kind": "review|tutorial|news|comparison|other",
  "summary_ko": "한국어 한 줄 요약"}}]
Return [] if you find nothing relevant."""


def cost(usage: dict[str, int]) -> float:
    return (usage.get("input_tokens", 0) * PRICE["input"]
            + usage.get("output_tokens", 0) * PRICE["output"]
            + usage.get("cache_read_input_tokens", 0) * PRICE["cache_read"]
            + usage.get("cache_creation_input_tokens", 0) * PRICE["cache_write"]) / 1_000_000 \
        + usage.get("web_search_requests", 0) * PRICE["search"]


def estimate() -> tuple[float, float]:
    lo = cost({"input_tokens": ASSUME["input"][0], "output_tokens": ASSUME["output"][0],
               "web_search_requests": ASSUME["searches"][0]})
    hi = cost({"input_tokens": ASSUME["input"][1], "output_tokens": ASSUME["output"][1],
               "web_search_requests": ASSUME["searches"][1]})
    return lo, hi


def descriptions() -> dict[str, str | None]:
    """시험 소급 랭킹에 남은 설명을 쓴다 (호출 0)."""
    out: dict[str, str | None] = {}
    for f in sorted((ROOT / ".work").glob("trial-data2/weekly/*/rankings.json")):
        for axis in json.loads(f.read_text(encoding="utf-8")).get("axes", {}).values():
            for e in axis.get("all") or []:
                out[e["full_name"]] = e.get("description")
    return out


def usage_of(resp: Any) -> dict[str, int]:
    u = resp.usage
    stu = getattr(u, "server_tool_use", None)
    return {
        "input_tokens": u.input_tokens or 0,
        "output_tokens": u.output_tokens or 0,
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
        "web_search_requests": (getattr(stu, "web_search_requests", 0) or 0) if stu else 0,
        "web_fetch_requests": (getattr(stu, "web_fetch_requests", 0) or 0) if stu else 0,
    }


def run_one(client: Any, name: str, desc: str | None) -> dict[str, Any]:
    user = PROMPT.format(name=name, desc=desc or "(none)")
    messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
    total: dict[str, int] = {}
    stops: list[str] = []
    resp = None
    for _ in range(4):  # pause_turn 은 이어서 요청한다 (최대 3번)
        resp = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS, tools=TOOLS, messages=messages)
        for k, v in usage_of(resp).items():
            total[k] = total.get(k, 0) + v
        stops.append(resp.stop_reason)
        if resp.stop_reason != "pause_turn":
            break
        messages = [{"role": "user", "content": user}, {"role": "assistant", "content": resp.content}]
    assert resp is not None
    text = "".join(b.text for b in resp.content if b.type == "text")
    try:
        start, end = text.index("["), text.rindex("]") + 1
        sources = json.loads(text[start:end])
    except ValueError:
        sources = None
    return {"repo": name, "usage": total, "cost_usd": round(cost(total), 4), "stop_reasons": stops,
            "sources": sources, "raw_text": None if sources is not None else text[:2000]}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="실제로 호출한다 (과금)")
    ap.add_argument("--budget", type=float, default=3.0, help="누적 비용 상한(달러)")
    args = ap.parse_args()
    descs = descriptions()
    lo, hi = estimate()
    print(f"모델 {MODEL} · 도구 {[t['type'] for t in TOOLS]} · max_tokens {MAX_TOKENS}")
    print(f"저장소 {len(REPOS)}개: {', '.join(REPOS)}")
    n = len(REPOS)
    print(f"추정(가정 {ASSUME}): 저장소당 ${lo:.2f}~${hi:.2f} · 합계 ${lo * n:.2f}~${hi * n:.2f}"
          f" · 상한 ${args.budget:.2f}")
    if not args.run:
        first = PROMPT.format(name=REPOS[0], desc=descs.get(REPOS[0]) or "(none)")
        print("\n[dry-run] 첫 요청 본문:\n" + first)
        print("\n호출하지 않았다. 실제로 재려면 --run")
        return 0

    import anthropic

    key = os.environ.get("STARTREND_ANTHROPIC_API_KEY")
    if not key:
        print("STARTREND_ANTHROPIC_API_KEY 가 없다", file=sys.stderr)
        return 2
    client = anthropic.Anthropic(api_key=key)
    results: list[dict[str, Any]] = []
    spent = 0.0
    for name in REPOS:
        if spent >= args.budget:
            print(f"상한 ${args.budget:.2f} 도달 — 멈춘다")
            break
        r = run_one(client, name, descs.get(name))
        spent += r["cost_usd"]
        results.append(r)
        u = r["usage"]
        found = len(r["sources"]) if isinstance(r["sources"], list) else "파싱 실패"
        print(f"{name:34} 입력 {u['input_tokens']:>7,} · 출력 {u['output_tokens']:>6,} · 검색 "
              f"{u['web_search_requests']} · fetch {u['web_fetch_requests']} · 출처 {found}"
              f" · ${r['cost_usd']:.3f} · {'/'.join(r['stop_reasons'])}")
    out = ROOT / ".work" / "measure" / f"web_search-{date.today().isoformat()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"model": MODEL, "tools": TOOLS, "results": results,
                               "total_usd": round(spent, 4)}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"합계 ${spent:.3f} · 결과 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
