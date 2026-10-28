"""python -m startrend <단계>

지금 있는 단계
- contract : GitHub API 계약 점검 (FR-11.6)
- probe    : 실측, 비용 0 (FR-12) — 결과는 .work/probe/<날짜>/, 응답 캐시는 .work/probe/cache/
- discover : 후보 발굴 + 전체 스냅샷, 비용 0 (FR-1) — .work/snapshots/<주>.csv, 응답 캐시는 주마다 따로
- stars    : 스냅샷 차이 + 상위 후보 히스토리 → data/stars/YYYY/<주>.csv (FR-2)
- backfill : 52주 소급 → 주간 파일들 (FR-2.4, 1회성 · 이어 돌리기)
- rank     : 주간 파일 → data/weekly/<주>/rankings.json · 메타 (FR-4)
- goldset  : 분류 정답 세트 후보 200개 → data/eval/goldset_candidates.jsonl (FR-14.1, 결정 41)
             캐시된 Search 응답에서 설명·토픽을 읽는다 — 네트워크 0, 토큰 불필요
- classify : AI 여부·유형·카테고리 판정 (FR-3) — 기본은 dry-run(호출 0). 실제 판정은 P2-9 승인 뒤
- trends   : 카테고리 추이 — 주마다 카테고리(+ALL) 증가 합계·저장소 수·AI 탭 진입 수 (FR-8.1), 호출 0
- eval     : 분류 평가 — 정답 세트로 판정 결과를 채점(호출 0) → data/eval/runs/ (FR-14). 결과 없으면 dry-run
- goldset-draft : 정답 세트 후보의 Claude 초안 (P2-11, 결정 41) — 기본은 dry-run(호출 0).
             --run 은 Batch 로 판정(과금)하고 블라인드 30개와 맞대어 채점한다
"""

import argparse
import base64
import io as _stdio
import json
import sys
import time
from collections.abc import Mapping
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from startrend.budget import BudgetMeter, run_batch
from startrend.clients.claude import ClaudeBatch, ClaudeLLM
from startrend.clients.decision import LLMDecider
from startrend.clients.github_live import LiveGitHub, cacheable_response
from startrend.clients.github_parse import GitHubFormatError, parse_repo, parse_search_page
from startrend.clients.llm import BatchItem, LLMRequest, MockLLM
from startrend.clients.transport import CachingTransport, UrllibTransport
from startrend.clients.trending import fetch_trending
from startrend.core import meta, snapshot, taxonomy, weekfile
from startrend.core import week as wk
from startrend.core.config import PROJECT_ROOT, ConfigError, Settings, load_settings
from startrend.core.io import dumps_json, read_json, read_jsonl, write_json, write_jsonl
from startrend.core.models import Repo
from startrend.stages import (
    backfill,
    classify,
    contract,
    discover,
    evaluate,
    goldset,
    probe,
    rank,
    stars,
    trends,
)


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    if isinstance(sys.stdout, _stdio.TextIOWrapper):  # 한국어 Windows(cp949) 대응
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="startrend")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("contract", help="GitHub API 계약 점검 — 오류면 종료 코드 1")
    p.add_argument("--repo", default=contract.DEFAULT_REPO)
    p.add_argument("--query", default=contract.DEFAULT_QUERY)
    p = sub.add_parser("probe", help="실측 (비용 0, GitHub API 호출 수백 회)")
    p.add_argument("--samples-per-bucket", type=int, default=20)
    p.add_argument("--readme-sample", type=int, default=60)
    p.add_argument("--seed", type=int, default=20261026)
    p = sub.add_parser("discover", help="후보 발굴 + 전체 스냅샷 (Search 약 1,000회, 비용 0)")
    p.add_argument("--pool-min", type=int, default=1000)
    p.add_argument("--new-days", type=int, default=30)
    p.add_argument("--new-min", type=int, default=10)
    p = sub.add_parser("stars", help="주간 스타 — 스냅샷 차이 + 상위 후보 히스토리 (비용 0)")
    p.add_argument("--week", help="주 시작일(일요일). 기본은 막 끝난 주")
    p = sub.add_parser("backfill", help="과거 N주 주간 파일 — 1회성, 오래 걸림 (비용 0)")
    p.add_argument("--weeks", type=int, default=52)
    p.add_argument("--limit", type=int, help="저장소 수 제한 (시험용)")
    p.add_argument("--top", type=int, help="스타가 가장 많은 N개만 (시험용)")
    p.add_argument("--new", type=int, help="새 저장소 중 스타가 가장 많은 N개만 (시험용, --top 과 합친다)")
    p = sub.add_parser("rank", help="주간 파일 → 4축 랭킹 (비용 0)")
    p.add_argument("--week", help="주 시작일(일요일). 기본은 막 끝난 주")
    p.add_argument("--all", action="store_true", help="주간 파일이 있는 모든 주를 오래된 순으로")
    p = sub.add_parser("goldset", help="분류 정답 세트 후보 200개 (캐시만 읽는다 — 비용 0, 호출 0)")
    p.add_argument("--week", help="스냅샷 주(일요일). 기본은 막 끝난 주")
    p.add_argument("--ranked-from", help="랭킹 진입 저장소를 읽을 데이터 폴더. 기본은 데이터 폴더")
    p.add_argument("--seed", type=int, default=20261027)
    p.add_argument("--more", type=int, help="블라인드 추가 N개(결정 50) → goldset_blind2_candidates.jsonl. "
                   "기존 후보는 빼고 덮어쓰지 않는다")
    p = sub.add_parser("classify", help="AI 여부·유형·카테고리 판정 — 기본은 dry-run(호출 0)")
    p.add_argument("--week", help="주 시작일(일요일). 기본은 막 끝난 주")
    p.add_argument("--all", action="store_true", help="랭킹이 있는 모든 주")
    p.add_argument("--run", action="store_true", help="실제 판정(과금) — dry-run 금액 승인 뒤")
    p = sub.add_parser("trends", help="카테고리 추이 — 주마다 카테고리(+ALL) 집계 (호출 0, 비용 0)")
    p.add_argument("--week", help="주 시작일(일요일). 기본은 막 끝난 주")
    p.add_argument("--all", action="store_true", help="주간 파일이 있는 모든 주")
    p = sub.add_parser("eval", help="분류 평가 — 정답 세트로 채점(호출 0). 판정 결과가 없으면 dry-run")
    p.add_argument("--gold", help="정답 라벨 jsonl. 기본은 data/eval/goldset_classify.jsonl")
    p.add_argument("--predictions", help="판정 결과 jsonl (goldset-draft 결과 등)")
    p.add_argument("--name", default="eval", help="실행 기록 이름 → data/eval/runs/<날짜>-<이름>")
    p.add_argument("--blind-only", action="store_true",
                   help="블라인드 행만 — 초안 없이 라벨한 주 기준(FR-14.1)")
    p = sub.add_parser("goldset-draft", help="정답 세트 후보 Claude 초안 — 기본은 dry-run(호출 0)")
    p.add_argument("--run", action="store_true", help="실제 판정(과금, Batch) — dry-run 금액 승인 뒤")
    p.add_argument("--cap", type=float, default=3.0,
                   help="이번 실행 예산 상한(달러) — 제출 전에 최악 비용으로 막는다")
    p.add_argument("--poll", type=float, default=60.0, help="Batch 상태 확인 간격(초)")
    args = ap.parse_args(argv)

    settings = load_settings(env=env)
    if args.cmd == "goldset":  # 네트워크를 쓰지 않는다 — 토큰 없이 돈다
        return _goldset(settings, args)
    if args.cmd == "classify":
        return _classify(settings, args)
    if args.cmd == "trends":  # 정본 파일만 읽는다 — 토큰 없이 돈다
        return _trends(settings, args)
    if args.cmd == "eval":
        return _eval(settings, args)
    if args.cmd == "goldset-draft":
        return _goldset_draft(settings, args)
    try:
        token = settings.require_github_token()
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 2

    if args.cmd == "contract":
        gh = LiveGitHub(token)
        report = contract.check_github(gh, repo=args.repo, query=args.query, today=date.today())
        print(dumps_json(report.to_dict()), end="")
        return 0 if report.ok else 1
    if args.cmd == "probe":
        return _probe(settings, token, args)
    if args.cmd == "discover":
        return _discover(settings, token, args)
    if args.cmd == "stars":
        return _stars(settings, token, args)
    if args.cmd == "backfill":
        return _backfill(settings, token, args)
    if args.cmd == "rank":
        return _rank(settings, token, args)
    return 2


def _log_wait(seconds: float, why: str) -> None:
    print(f"  레이트 리밋 대기 {seconds:.0f}초 — {why}", flush=True)


def _probe(settings: Settings, token: str, args: argparse.Namespace) -> int:
    today = date.today()
    out = settings.work_dir / "probe" / today.isoformat()
    cache = CachingTransport(UrllibTransport(), settings.work_dir / "probe" / "cache", cacheable_response)
    gh = LiveGitHub(token, on_wait=_log_wait, transport=cache)
    report = probe.run_probe(
        gh,
        fetch_html=lambda url: fetch_trending(cache, "weekly"),
        today=today,
        out_dir=out,
        samples_per_bucket=args.samples_per_bucket,
        readme_sample=args.readme_sample,
        seed=args.seed,
        log=lambda m: print(m, flush=True),
    )
    report["network"] = {
        "requests_sent": cache.misses,
        "cache_hits": cache.hits,
        "seconds_per_request": probe.percentiles(cache.miss_seconds, [50, 90]),
        "rate_limit_wait_seconds": round(gh.stats.rate_waits, 1),
    }
    write_json(out / "report.json", report)
    print(f"보고서: {out / 'report.json'}", flush=True)
    return 0


def _discover(settings: Settings, token: str, args: argparse.Namespace) -> int:
    today = date.today()
    # 스냅샷은 막 끝난 주(지난 주)의 끝 상태다.
    # 캐시는 그 주 안에서만 다시 쓴다 — 다음 주에 오래된 값이 섞이지 않게
    week =wk.week_name(wk.previous_week(wk.week_start(today)))
    cache = CachingTransport(UrllibTransport(), settings.work_dir / "cache" / week, cacheable_response)
    gh = LiveGitHub(token, on_wait=_log_wait, transport=cache)
    result = discover.discover(gh, today=today, pool_min=args.pool_min, new_days=args.new_days,
                               new_min=args.new_min, log=lambda m: print(m, flush=True))
    snap = settings.work_dir / "snapshots" / f"{week}.csv"
    snapshot.write(snap, result.rows)
    stats = {**result.stats, "week": week, "run_date": today.isoformat(),
             "network": {"requests_sent": cache.misses, "cache_hits": cache.hits,
                         "rate_limit_wait_seconds": round(gh.stats.rate_waits, 1)},
             "calls": dict(gh.stats.calls)}
    write_json(settings.work_dir / week / "discover.json", stats)
    print(dumps_json(stats), end="")
    print(f"스냅샷: {snap} ({len(result.rows)}개)", flush=True)
    return 0


def _last_full_week(today: date) -> date:
    return wk.previous_week(wk.week_start(today))


def _week_arg(value: str | None, today: date) -> date:
    return wk.parse_week(value) if value else _last_full_week(today)


def _snapshot_path(settings: Settings, w: date) -> Path:
    return settings.work_dir / "snapshots" / f"{wk.week_name(w)}.csv"


def _stars(settings: Settings, token: str, args: argparse.Namespace) -> int:
    today = date.today()
    w = _week_arg(args.week, today)
    cur_path = _snapshot_path(settings, w)
    if not cur_path.exists():
        print(f"이번 주 스냅샷이 없다 — 먼저 discover: {cur_path}", file=sys.stderr)
        return 2
    prev_path = _snapshot_path(settings, w - timedelta(days=7))
    prev = snapshot.read(prev_path) if prev_path.exists() else None
    cache = CachingTransport(UrllibTransport(), settings.work_dir / "cache" / wk.week_name(w),
                             cacheable_response)
    gh = LiveGitHub(token, on_wait=_log_wait, transport=cache)
    tracked = rank.tracked_names(settings.data_dir, w - timedelta(days=7))
    stats = stars.run_stars(gh, cur=snapshot.read(cur_path), prev=prev, week_start=w, today=today,
                            data_dir=settings.data_dir, tracked=tracked,
                            log=lambda m: print(m, flush=True))
    print(dumps_json(stats), end="")
    return 0


def select_rows(rows: list[snapshot.SnapRow], *, top: int | None = None, new: int | None = None,
                limit: int | None = None) -> list[snapshot.SnapRow]:
    """시험 소급용 표본. --top·--new 가 없으면 전부(ID 순)."""
    picked: dict[int, snapshot.SnapRow] = {}
    by_stars = sorted(rows, key=lambda r: (-r.stars, r.id))
    if top:
        picked.update((r.id, r) for r in by_stars[:top])
    if new:
        picked.update((r.id, r) for r in [r for r in by_stars if "new" in r.sources][:new])
    out = sorted(picked.values() if (top or new) else rows, key=lambda r: r.id)
    return out[:limit] if limit else out


def _backfill(settings: Settings, token: str, args: argparse.Namespace) -> int:
    today = date.today()
    w = _last_full_week(today)
    snap_path = _snapshot_path(settings, w)
    if not snap_path.exists():
        print(f"스냅샷이 없다 — 먼저 discover: {snap_path}", file=sys.stderr)
        return 2
    rows = select_rows(list(snapshot.read(snap_path).values()), top=args.top, new=args.new, limit=args.limit)
    # 같은 주 안에서는 이어 돌린다 — 캐시를 대상 주 단위로 둔다
    cache = CachingTransport(UrllibTransport(), settings.work_dir / "cache" / f"backfill-{wk.week_name(w)}",
                             cacheable_response)
    gh = LiveGitHub(token, on_wait=_log_wait, transport=cache, max_rate_wait=3700.0, max_rate_waits=100)
    stats = backfill.run_backfill(gh, rows=rows, today=today, weeks_back=args.weeks,
                                  data_dir=settings.data_dir,
                                  log=lambda m: print(m, flush=True))
    stats["network"] = {"requests_sent": cache.misses, "cache_hits": cache.hits,
                        "rate_limit_wait_seconds": round(gh.stats.rate_waits, 1)}
    write_json(settings.work_dir / wk.week_name(w) / "backfill.json", stats)
    print(dumps_json({k: v for k, v in stats.items() if k != "rows_per_week"}), end="")
    return 0


def _rank(settings: Settings, token: str, args: argparse.Namespace) -> int:
    today = date.today()
    if args.all:
        files = sorted((settings.data_dir / "stars").glob("*/*.csv"))
        weeks = [wk.parse_week(f.stem) for f in files]
    else:
        weeks = [_week_arg(args.week, today)]
    cache = CachingTransport(UrllibTransport(), settings.work_dir / "cache" / "rank", cacheable_response)
    gh = LiveGitHub(token, on_wait=_log_wait, transport=cache)
    classified = meta.classified(settings.data_dir)   # AI 탭(P2-6) — 판정 결과 색인을 한 번만 만든다
    for w in weeks:
        if not weekfile.week_path(settings.data_dir, w).exists():
            print(f"주간 파일이 없다: {w}", file=sys.stderr)
            return 2
        snap_path = _snapshot_path(settings, w)
        extra = None
        if snap_path.exists():  # 증가가 적은 큰 저장소도 누적 축에 넣는다
            extra = {r.id: weekfile.WeekRow(r.id, r.full_name, r.created, r.stars, 0, False, None)
                     for r in snapshot.read(snap_path).values()}
        stats = rank.run_rank(gh, week_start=w, data_dir=settings.data_dir, extra_totals=extra,
                              classified=classified, log=lambda m: print(m, flush=True))
        print(f"{stats['week']}: 랭킹 진입 {stats['entrants']}개 · 저장소 조회 {stats['repo_calls']}회",
              flush=True)
    return 0


def cached_repos(cache_dir: Path, wanted: set[int]) -> dict[int, Repo]:
    """CachingTransport 가 남긴 Search·저장소 응답에서 wanted 저장소의 메타를 꺼낸다 (호출 0)."""
    found: dict[int, Repo] = {}
    for f in sorted(cache_dir.glob("*.json")) if cache_dir.exists() else []:
        d = json.loads(f.read_text(encoding="utf-8"))
        url = str(d.get("url", ""))
        if d.get("status") != 200:
            continue
        try:
            body = json.loads(base64.b64decode(d["body"]))
            if "/search/repositories" in url:
                repos = list(parse_search_page(body).items)
            elif "/repos/" in url and url.count("/") == 5:  # https://api.github.com/repos/{owner}/{repo}
                repos = [parse_repo(body)]
            else:
                continue
        except (ValueError, GitHubFormatError):
            continue
        found.update((r.id, r) for r in repos if r.id in wanted)
    return found


def ranked_ids(data_dir: Path) -> set[int]:
    ids: set[int] = set()
    for f in sorted((data_dir / "weekly").glob("*/rankings.json")):
        for axis in read_json(f).get("axes", {}).values():
            ids.update(e["id"] for e in (axis.get("all") or []))
    return ids


def _goldset(settings: Settings, args: argparse.Namespace) -> int:
    w = _week_arg(args.week, date.today())
    snap_path = _snapshot_path(settings, w)
    if not snap_path.exists():
        print(f"스냅샷이 없다 — 먼저 discover: {snap_path}", file=sys.stderr)
        return 2
    snap = snapshot.read(snap_path)
    repos = cached_repos(settings.work_dir / "cache" / wk.week_name(w), set(snap))
    ranked = ranked_ids(Path(args.ranked_from) if args.ranked_from else settings.data_dir)
    new = {rid for rid, r in snap.items() if "new" in r.sources}
    ev_dir = settings.data_dir / "eval"
    if args.more:
        out = ev_dir / "goldset_blind2_candidates.jsonl"
        if out.exists():
            print(f"이미 있다 — 덮어쓰지 않는다: {out}", file=sys.stderr)
            return 2
        first = ev_dir / "goldset_candidates.jsonl"
        taken = {int(p["repo_id"]) for p in read_jsonl(first)} if first.exists() else set()
        picks = goldset.sample_more(repos, ranked=ranked, new=new, exclude=taken, n=args.more,
                                    seed=args.seed + 1)
    else:
        out = ev_dir / "goldset_candidates.jsonl"
        picks = goldset.sample(repos, ranked=ranked, new=new, seed=args.seed)
    write_jsonl(out, picks)
    groups: dict[str, int] = {}
    for p in picks:
        groups[p["group"]] = groups.get(p["group"], 0) + 1
    print(dumps_json({"snapshot": len(snap), "with_meta": len(repos), "ranked_pool": len(ranked & set(repos)),
                      "picked": len(picks), "groups": groups, "blind": sum(p["blind"] for p in picks),
                      "out": str(out)}), end="")
    return 0


def _load_taxonomy(settings: Settings) -> taxonomy.Taxonomy:
    # 분류 체계는 데이터 폴더에 있으면 그것, 없으면(시험·임시 폴더) 저장소의 정본을 쓴다
    tax_file = settings.data_dir / "taxonomy.toml"
    return taxonomy.load(tax_file if tax_file.exists() else PROJECT_ROOT / "data" / "taxonomy.toml")


def _classify(settings: Settings, args: argparse.Namespace) -> int:
    if args.run:
        print("실제 판정은 아직 열지 않았다 — 정답 세트 비교(D-16)와 dry-run 금액 승인(P2-9) 뒤에 연다 "
              "(Batch 경로 P2-2 는 준비됨)", file=sys.stderr)
        return 2
    if args.all:
        files = sorted((settings.data_dir / "weekly").glob("*/rankings.json"))
        weeks = [wk.parse_week(f.parent.name) for f in files]
    else:
        weeks = [_week_arg(args.week, date.today())]
    tax = _load_taxonomy(settings)
    system = LLMDecider(MockLLM([]), tax).system
    est = classify.dry_run(data_dir=settings.data_dir, weeks=weeks, system_prompt=system)
    print(dumps_json({"dry_run": True, "weeks": [wk.week_name(w) for w in weeks], **est}), end="")
    return 0


def _trends(settings: Settings, args: argparse.Namespace) -> int:
    if args.all:
        weeks = [wk.parse_week(f.stem) for f in sorted((settings.data_dir / "stars").glob("*/*.csv"))]
    else:
        weeks = [_week_arg(args.week, date.today())]
    for w in weeks:
        if not weekfile.week_path(settings.data_dir, w).exists():
            print(f"주간 파일이 없다: {w}", file=sys.stderr)
            return 2
    classified = meta.classified(settings.data_dir)
    stats = trends.run_trends(data_dir=settings.data_dir, weeks=weeks, tax=_load_taxonomy(settings),
                              classified=classified, log=lambda m: print(m, flush=True))
    print(dumps_json({**stats, "classified": len(classified)}), end="")
    return 0


def _eval_summary(r: Mapping[str, Any], run: Path) -> dict[str, Any]:
    return {"run": str(run), "n": r["n"], "answered": r["answered"], "unanswered": r["unanswered"],
            "is_ai_accuracy": r["is_ai"]["accuracy"], "is_ai_accuracy_strict": r["is_ai"]["accuracy_strict"],
            "type_accuracy": r["type"]["accuracy"], "category_accuracy": r["category"]["accuracy"],
            "category_macro_f1": r["category"]["macro_f1"], "calibration_error": r["calibration_error"],
            "disagreements": len(r["disagreements"])}


def _eval(settings: Settings, args: argparse.Namespace) -> int:
    tax = _load_taxonomy(settings)
    gold_path = Path(args.gold) if args.gold else settings.data_dir / "eval" / "goldset_classify.jsonl"
    if not gold_path.exists():
        print(f"정답 파일이 없다: {gold_path} — --gold 로 지정한다", file=sys.stderr)
        return 2
    gold = evaluate.load_labels(gold_path, tax, blind_only=args.blind_only)
    if not args.predictions:
        est = evaluate.dry_run(n_items=len(gold), system_prompt=LLMDecider(MockLLM([]), tax).system)
        print(dumps_json({"dry_run": True, "gold": str(gold_path), **est}), end="")
        return 0
    pred_path = Path(args.predictions)
    result = evaluate.score(gold, evaluate.load_predictions(pred_path))
    md = evaluate.report_md(result, title=f"분류 평가 — {args.name}", tax=tax,
                            notes=[f"정답: `{gold_path.name}` ({len(gold)}개)", f"판정: `{pred_path.name}`"])
    run = evaluate.write_run(settings.data_dir, args.name,
                             {"gold": gold_path.name, "predictions": pred_path.name, **result}, md)
    print(dumps_json(_eval_summary(result, run)), end="")
    return 0


def _goldset_draft(settings: Settings, args: argparse.Namespace) -> int:
    cand_path = settings.data_dir / "eval" / "goldset_candidates.jsonl"
    if not cand_path.exists():
        print(f"후보 파일이 없다 — 먼저 goldset: {cand_path}", file=sys.stderr)
        return 2
    candidates = list(read_jsonl(cand_path))
    tax = _load_taxonomy(settings)
    out = settings.data_dir / "eval" / "goldset_drafts.jsonl"
    if not args.run:
        est = evaluate.dry_run(n_items=len(candidates), system_prompt=LLMDecider(MockLLM([]), tax).system)
        print(dumps_json({"dry_run": True, "candidates": len(candidates),
                          "blind": sum(1 for c in candidates if c.get("blind")),
                          "github_calls": 2 * len(candidates), "cap_usd": args.cap, "out": str(out), **est}),
              end="")
        return 0
    try:
        token = settings.require_github_token()
        key = settings.require_anthropic_key()
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 2

    def log(m: str) -> None:
        print(m, flush=True)

    cache = CachingTransport(UrllibTransport(), settings.work_dir / "cache" / "goldset", cacheable_response)
    gh = LiveGitHub(token, on_wait=_log_wait, transport=cache)
    meter = BudgetMeter(ClaudeLLM(key), cap_usd=args.cap)   # 일반 호출(거절 → 대체 모델)도 같은 상한
    decider = LLMDecider(meter, tax)
    batch_client = ClaudeBatch(key)
    states = settings.work_dir / "batches"

    def runner(reqs: dict[str, LLMRequest], tag: str) -> dict[str, BatchItem]:
        return run_batch(meter, batch_client, reqs, state=states / f"goldset-draft-{tag}.json",
                         poll_seconds=args.poll, log=log)

    t0 = time.monotonic()
    stats = goldset.run_draft(gh, decider, candidates, out=out, batch=runner, log=log)
    seconds = time.monotonic() - t0
    report = None
    blind_path = settings.data_dir / "eval" / "goldset_blind_labels.jsonl"
    # 블라인드 30 대 초안 — 초안 편향을 잰다 (FR-14.1). 이번 실행에서 판정한 것이 없으면 기록하지 않는다
    if blind_path.exists() and out.exists() and stats["decided"]:
        result = evaluate.score(evaluate.load_labels(blind_path, tax), evaluate.load_predictions(out))
        md = evaluate.report_md(result, title="블라인드 30 대 Claude 초안", tax=tax, notes=[
            "정답: 블라인드 30 — 사용자가 다른 AI 의 분류를 검토해 옮긴 라벨(FR-14.1)",
            f"판정: Claude 초안 `{out.name}` · 판정기 `{decider.fingerprint}`",
            f"이번 실행 전체 비용 ${meter.spent:.2f} (후보 {len(candidates)}개, Batch)"])
        report = evaluate.write_run(settings.data_dir, "blind30-vs-claude-draft",
                                    {"gold": blind_path.name, "predictions": out.name, **result}, md)
    summary = {**stats, "spent_usd": round(meter.spent, 4), "calls": meter.calls,
               "batch_calls": sum(1 for e in meter.ledger if e["batch"]), "seconds": round(seconds),
               "out": str(out), "blind_report": str(report) if report else None}
    write_json(settings.work_dir / "goldset-draft" / f"{date.today().isoformat()}.json",
               {**summary, "ledger": meter.ledger})
    print(dumps_json(summary), end="")
    return 0 if stats["stopped"] is None else 3


if __name__ == "__main__":
    raise SystemExit(main())
