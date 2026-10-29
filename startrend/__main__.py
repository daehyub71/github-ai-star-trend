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
- classify : AI 여부·유형·카테고리 판정 (FR-3) — 기본은 dry-run(호출 0). --run 은 Batch 조각으로 판정(과금)
- trends   : 카테고리 추이 — 주마다 카테고리(+ALL) 증가 합계·저장소 수·AI 탭 진입 수 (FR-8.1), 호출 0
- evidence : 근거 수집 (FR-5) — 그 주 AI 탭 저장소의 GitHub·HN·GeekNews·패키지·웹 검색 근거
             → .work/<주>/evidence.jsonl. 기본은 계획만(호출 0). --run 은 무료 API·Tavily 무료 크레딧
- analyze  : 심층 카드 (FR-6) — 근거 + 숫자 → 8섹션 카드, 인용 게이트 → .work/<주>/cards/ (D-23 전까지).
             기본은 dry-run(호출 0). --run 은 일반 호출(과금, --cap 상한).
             다시 들어온 저장소는 변경 기록만(비용 0)
- brief    : 주간 브리핑 (FR-8) — 랭킹·카테고리 추이·카드 → .work/<주>/briefing.md (결정 53).
             기본은 dry-run(호출 0). --run 은 주 1회 호출(과금)
- export   : 사이트 파생 데이터 (FR-9) — data/site/(공개) + .work/site-private/(카드·브리핑, 결정 53), 호출 0
- weekly   : 주간 실행 (FR-11) — contract → discover → stars → rank → classify → rank → trends →
             evidence → analyze → check → brief → export. 기본은 계획만(호출 0).
             --run 은 LLM 단계들이 예산 하나(기본 주 $10)를 함께 쓴다. 끝에 archive(압축만)
- archive  : 주간 압축본 (FR-10) — evidence-<주>.tar.gz(근거 원문 + LLM 로그) · snapshot-<주>.csv.gz.
             시크릿 검사에 걸리면 만들지 않는다. 올리기는 워크플로(결정 55)
- private  : 비공개 저장소 체크아웃 ↔ .work/ (FR-11.8, 결정 55) — 카드 보관소·주별 카드·브리핑·사이트 사본
- eval     : 분류 평가 — 정답 세트로 판정 결과를 채점(호출 0) → data/eval/runs/ (FR-14). 결과 없으면 dry-run
- goldset-draft : 정답 세트 후보의 Claude 초안 (P2-11, 결정 41) — 기본은 dry-run(호출 0).
             --run 은 Batch 로 판정(과금)하고 블라인드 30개와 맞대어 채점한다
- notion-setup : Notion 데이터베이스 3개(주간 · 저장소 카드 · 블로그 초안) — 한 번만(FR-15.5)
- notion   : 그 주 카드·주간 페이지를 Notion 에(FR-15). 기본은 계획만(호출 0).
             상태가 '초안'인 페이지만 고친다.
             대응표는 .work/notion/index.json(결정 59 — 공개 저장소에 올리지 않는다)
"""

import argparse
import base64
import hashlib
import io as _stdio
import json
import os
import sys
import time
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from startrend.budget import BudgetMeter, run_batch
from startrend.clients import repo_images
from startrend.clients.claude import ClaudeBatch, ClaudeLLM
from startrend.clients.decision import LLMDecider
from startrend.clients.evidence import web
from startrend.clients.evidence.base import EvidenceSource
from startrend.clients.evidence.geeknews import GeekNewsSource
from startrend.clients.evidence.github import GitHubSource
from startrend.clients.evidence.hn import HNSource
from startrend.clients.evidence.packages import PackagesSource
from startrend.clients.github import GitHubError
from startrend.clients.github_live import LiveGitHub, cacheable_response
from startrend.clients.github_parse import GitHubFormatError, parse_repo, parse_search_page
from startrend.clients.llm import BatchItem, LLMRequest, MockLLM
from startrend.clients.notion import NotionError
from startrend.clients.notion import status_name as notion_status
from startrend.clients.notion_live import LiveNotion
from startrend.clients.transport import CachingTransport, TransportError, UrllibPoster, UrllibTransport
from startrend.clients.trending import fetch_trending
from startrend.core import meta, secrets, snapshot, taxonomy, weekfile
from startrend.core import week as wk
from startrend.core.config import PROJECT_ROOT, ConfigError, Settings, load_settings
from startrend.core.io import dumps_json, read_json, read_jsonl, write_json, write_jsonl
from startrend.core.models import Repo
from startrend.stages import (
    analyze,
    archive,
    backfill,
    blog,
    brief,
    classify,
    contract,
    discover,
    evaluate,
    evidence,
    export,
    goldset,
    notion,
    private,
    probe,
    rank,
    stars,
    trends,
    weekly,
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
    p.add_argument("--cap", type=float, default=10.0,
                   help="이번 실행 예산 상한(달러) — 주간 기본 $10(결정 31). 첫 전수 분류는 승인한 금액")
    p.add_argument("--chunk", type=int, default=400,
                   help="한 Batch 에 보낼 최대 건수 — 실제 지출로 상한을 지킨다")
    p.add_argument("--poll", type=float, default=60.0, help="Batch 상태 확인 간격(초)")
    p.add_argument("--no-batch", action="store_true", help="Batch 대신 일반 호출 — 빠르지만 할인 없음(2배)")
    p = sub.add_parser("trends", help="카테고리 추이 — 주마다 카테고리(+ALL) 집계 (호출 0, 비용 0)")
    p.add_argument("--week", help="주 시작일(일요일). 기본은 막 끝난 주")
    p.add_argument("--all", action="store_true", help="주간 파일이 있는 모든 주")
    p = sub.add_parser("evidence",
                       help="근거 수집(FR-5) — 기본은 계획만(호출 0). --run 은 무료 API·검색 크레딧")
    p.add_argument("--week", help="주 시작일(일요일). 기본은 막 끝난 주")
    p.add_argument("--repos", help="쉼표로 구분 — 그 주 AI 탭에서 이 저장소만")
    p.add_argument("--run", action="store_true", help="실제로 모은다 — GitHub·HN·GeekNews·패키지·웹 검색")
    p.add_argument("--no-web", action="store_true", help="웹 검색(Tavily 크레딧)을 쓰지 않는다")
    p.add_argument("--only-missing", action="store_true",
                   help="그 주 근거 목록에 아직 없는 저장소만 — 이어 모을 때 크레딧을 다시 쓰지 않는다")
    p = sub.add_parser("analyze", help="심층 카드(FR-6) — 기본은 dry-run(호출 0). --run 은 과금")
    p.add_argument("--week", help="주 시작일(일요일). 기본은 막 끝난 주")
    p.add_argument("--repos", help="쉼표로 구분 — 근거를 모은 저장소 중 이것만")
    p.add_argument("--run", action="store_true", help="실제 생성(과금) — dry-run 금액 승인 뒤")
    p.add_argument("--cap", type=float, default=3.0,
                   help="이번 실행 예산 상한(달러) — 부르기 전 최악 비용으로 막는다")
    p.add_argument("--effort", default=analyze.EFFORT, choices=["low", "medium", "high"])
    p.add_argument("--check", action="store_true", help="그 주에 쓴 카드의 품질 검사만(호출 0, FR-14.4)")
    p.add_argument("--adopt", action="store_true",
                   help="그 주에 쓴 카드를 최신 카드 보관소에 넣기만(호출 0) — "
                        "다음 주에 '다시 등장'으로 이어진다")
    p.add_argument("--force-new", action="store_true",
                   help="보관소에 카드가 있어도 새로 쓴다(과금). 기본은 다시 등장하면 변경 기록만(비용 0)")
    p = sub.add_parser("brief", help="주간 브리핑(FR-8) — 기본은 dry-run(호출 0). --run 은 과금(주 1회 호출)")
    p.add_argument("--week", help="주 시작일(일요일). 기본은 막 끝난 주")
    p.add_argument("--run", action="store_true", help="실제 생성(과금) — dry-run 금액 승인 뒤")
    p.add_argument("--cap", type=float, default=1.0, help="이번 실행 예산 상한(달러)")
    sub.add_parser("export", help="사이트 파생 데이터(FR-9) — data/site/ + 비공개 카드·브리핑 사본(호출 0)")
    p = sub.add_parser("weekly", help="주간 실행(FR-11) — 기본은 계획만(호출 0). --run 은 과금(주 예산 상한)")
    p.add_argument("--week", help="주 시작일(일요일). 기본은 막 끝난 주 — discover 는 그 주만 찍는다")
    p.add_argument("--run", action="store_true", help="실제 실행 — 계획 금액 확인 뒤")
    p.add_argument("--cap", type=float, default=10.0, help="이번 실행 전체 LLM 예산(달러) — 결정 31 주 $10")
    p.add_argument("--no-web", action="store_true", help="근거 수집에서 웹 검색(Tavily 크레딧)을 쓰지 않는다")
    p.add_argument("--poll", type=float, default=60.0, help="Batch 상태 확인 간격(초)")
    p = sub.add_parser("archive", help="주간 압축본(FR-10) — 시크릿 검사 뒤 .work/archive/<주>/ (호출 0)")
    p.add_argument("--week", help="주 시작일(일요일). 기본은 막 끝난 주")
    p = sub.add_parser("private", help="비공개 저장소 체크아웃 ↔ .work/ 복사(결정 55, 호출 0)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--pull", metavar="DIR", help="비공개 저장소 체크아웃 → .work/")
    g.add_argument("--push", metavar="DIR", help=".work/ → 비공개 저장소 체크아웃")
    p = sub.add_parser("blog", help="블로그 초안(FR-16) — 기본은 dry-run(호출 0). --run 은 과금(주 1회 호출)")
    p.add_argument("--week", help="주 시작일(일요일). 기본은 막 끝난 주")
    p.add_argument("--run", action="store_true", help="실제 생성(과금) — dry-run 금액 승인 뒤")
    p.add_argument("--cap", type=float, default=1.0, help="이번 실행 예산 상한(달러)")
    p = sub.add_parser("notion-setup",
                       help="Notion 데이터베이스 3개(FR-15.5, 한 번만) — 기본은 계획만(호출 0)")
    p.add_argument("--parent", required=True,
                   help="부모 페이지 ID — 연결(github-ai-star-trend)을 공유한 페이지")
    p.add_argument("--run", action="store_true", help="실제로 만든다(Notion API, 비용 0)")
    p = sub.add_parser("notion",
                       help="주간·카드·블로그 초안 페이지를 Notion 에(FR-15) — 기본은 계획만(호출 0)")
    p.add_argument("--week", help="주 시작일(일요일). 기본은 막 끝난 주")
    p.add_argument("--run", action="store_true",
                   help="실제로 올린다(Notion API, 비용 0) — 상태가 '초안'인 페이지만 고친다(NFR-16)")
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
    p.add_argument("--blind-only", action="store_true", help="블라인드 후보만(1차 + 2차) — 재측정용(결정 50)")
    p.add_argument("--out", default="goldset_drafts",
                   help="결과 파일 이름 data/eval/<이름>.jsonl — 있으면 덮어쓰지 않는다")
    p.add_argument("--no-batch", action="store_true", help="Batch 대신 일반 호출 — 빠르지만 할인 없음(2배)")
    args = ap.parse_args(argv)

    settings = load_settings(env=env)
    # archive 시크릿 검사용 실제 키 값 — 출력하지 않는다
    args.secrets = secrets.secret_values(os.environ if env is None else env)
    if args.cmd == "goldset":  # 네트워크를 쓰지 않는다 — 토큰 없이 돈다
        return _goldset(settings, args)
    if args.cmd == "classify":
        return _classify(settings, args)
    if args.cmd == "trends":  # 정본 파일만 읽는다 — 토큰 없이 돈다
        return _trends(settings, args)
    if args.cmd == "evidence":  # 계획은 토큰 없이, --run 은 스스로 키를 확인한다
        return _evidence(settings, args)
    if args.cmd == "analyze":   # dry-run 은 키 없이
        return _analyze(settings, args)
    if args.cmd == "brief":     # dry-run 은 키 없이
        return _brief(settings, args)
    if args.cmd == "export":    # 정본만 읽는다 — 키·네트워크 없이
        stats = export.run_export(data_dir=settings.data_dir, work_dir=settings.work_dir,
                                  log=lambda m: print(m, flush=True))
        print(dumps_json(stats), end="")
        return 0
    if args.cmd == "eval":
        return _eval(settings, args)
    if args.cmd == "weekly":   # 계획은 키 없이, --run 은 스스로 키를 확인한다
        return _weekly(settings, args)
    if args.cmd == "archive":  # 파일만 — 키·네트워크 없이
        return _archive(settings, args)
    if args.cmd == "private":  # 파일 복사만
        return _private(settings, args)
    if args.cmd == "notion-setup":   # 계획은 토큰 없이, --run 은 스스로 토큰을 확인한다
        return _notion_setup(settings, args)
    if args.cmd == "notion":
        return _notion(settings, args)
    if args.cmd == "blog":     # dry-run 은 키 없이
        return _blog(settings, args)
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


def _classify(settings: Settings, args: argparse.Namespace, meter: BudgetMeter | None = None) -> int:
    if args.all:
        files = sorted((settings.data_dir / "weekly").glob("*/rankings.json"))
        weeks = [wk.parse_week(f.parent.name) for f in files]
    else:
        weeks = [_week_arg(args.week, date.today())]
    tax = _load_taxonomy(settings)
    if not args.run:
        system = LLMDecider(MockLLM([]), tax).system
        est = classify.dry_run(data_dir=settings.data_dir, weeks=weeks, system_prompt=system)
        print(dumps_json({"dry_run": True, "weeks": [wk.week_name(w) for w in weeks], **est}), end="")
        return 0
    try:
        token = settings.require_github_token()
        key = settings.require_anthropic_key()
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 2

    def log(m: str) -> None:
        print(m, flush=True)

    cache = CachingTransport(UrllibTransport(), settings.work_dir / "cache" / "classify", cacheable_response)
    # 첫 전수 분류는 GitHub 호출이 수천 번이다 — 시간당 한도에 걸리면 풀릴 때까지 기다린다(빠뜨리지 않게)
    gh = LiveGitHub(token, on_wait=_log_wait, transport=cache, max_rate_wait=3700.0, max_rate_waits=100)
    # 일반 호출(거절 → 대체 모델)도 같은 상한. weekly 는 단계들이 계량기 하나를 함께 쓴다(FR-11.2)
    meter = meter or BudgetMeter(ClaudeLLM(key), cap_usd=args.cap)
    decider = LLMDecider(meter, tax)
    batch_client = ClaudeBatch(key)
    states = settings.work_dir / "batches"

    def runner(reqs: dict[str, LLMRequest], tag: str) -> dict[str, BatchItem]:
        # 상태 파일 이름은 보낸 항목 목록으로 — 끊겼다 다시 돌 때 순번이 바뀌어도 같은 묶음을 이어 받는다
        ids = hashlib.sha256(",".join(sorted(reqs)).encode()).hexdigest()[:16]
        log(f"  Batch {tag}: {len(reqs)}건")
        return run_batch(meter, batch_client, reqs, state=states / f"classify-{ids}.json",
                         poll_seconds=args.poll, log=log)

    t0 = time.monotonic()
    stats = classify.run_classify(gh, decider, data_dir=settings.data_dir, weeks=weeks,
                                  batch=None if args.no_batch else runner, chunk=args.chunk, log=log)
    summary = {**{k: v for k, v in stats.items() if k not in ("unclassified", "missing")},
               "unclassified": len(stats["unclassified"]), "missing": len(stats["missing"]),
               "spent_usd": round(meter.spent, 4), "cap_usd": args.cap, "calls": meter.calls,
               "batch_calls": sum(1 for e in meter.ledger if e["batch"]),
               "seconds": round(time.monotonic() - t0), "fingerprint": decider.fingerprint,
               "weeks": len(weeks)}
    write_json(settings.work_dir / "classify" / f"{date.today().isoformat()}.json",
               {**summary, "unclassified_names": stats["unclassified"], "missing_names": stats["missing"],
                "ledger": meter.ledger})
    print(dumps_json(summary), end="")
    return 0 if stats["stopped"] is None else 3


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


def _evidence(settings: Settings, args: argparse.Namespace) -> int:
    w = _week_arg(args.week, date.today())
    repos = [r.strip() for r in args.repos.split(",") if r.strip()] if args.repos else None
    try:
        targets = evidence.targets_for(settings.data_dir, w, repos=repos)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2
    if args.only_missing:
        have = set(evidence.read(settings.work_dir, w))
        targets = [t for t in targets if t.repo_id not in have]
    queries = 0 if args.no_web else len(web.default_queries(targets[0])) if targets else 3
    if not args.run:
        est = evidence.plan(targets, web_queries=queries)
        print(dumps_json({"plan": True, "week": wk.week_name(w), **est}), end="")
        return 0
    try:
        token = settings.require_github_token()
        tavily_key = None if args.no_web else settings.require_tavily_key()
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 2

    def log(m: str) -> None:
        print(m, flush=True)

    # 응답 캐시는 주마다 따로 — 다음 주에 지난 주의 저장소 정보·검색 결과를 다시 쓰지 않게
    cache = CachingTransport(UrllibTransport(), settings.work_dir / "cache" / "evidence" / wk.week_name(w),
                             cacheable_response)
    gh = LiveGitHub(token, on_wait=_log_wait, transport=cache)
    geeknews = GeekNewsSource(cache)
    search = web.TavilySource(UrllibPoster(), tavily_key) if tavily_key else None
    sources: list[EvidenceSource] = [GitHubSource(gh), HNSource(cache), geeknews, PackagesSource(cache)]
    if search:
        sources.append(search)
    t0 = time.monotonic()
    stats = evidence.run_evidence(sources, targets, work_dir=settings.work_dir, week_start=w, log=log)
    print(dumps_json({**stats, "week": wk.week_name(w), "tavily_credits": search.credits if search else 0,
                      "geeknews_requests": geeknews.calls, "github_calls": dict(gh.stats.calls),
                      "cache_hits": cache.hits, "seconds": round(time.monotonic() - t0),
                      "file": str(evidence.evidence_path(settings.work_dir, w))}), end="")
    return 0


def _analyze(settings: Settings, args: argparse.Namespace, meter: BudgetMeter | None = None) -> int:
    w = _week_arg(args.week, date.today())
    if args.check:
        res = analyze.check_week(settings.data_dir, settings.work_dir, w)
        ok = sum(q["ok"] for q in res.values())
        print(dumps_json({"week": wk.week_name(w), "cards": len(res), "ok": ok, "results": res}), end="")
        return 0 if all(q["ok"] for q in res.values()) else 1
    repos = [r.strip() for r in args.repos.split(",") if r.strip()] if args.repos else None
    try:
        inputs = analyze.load_inputs(settings.data_dir, settings.work_dir, w, repos=repos)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2
    if not inputs:
        print(f"카드를 만들 근거가 없다 — 먼저 `evidence --week {wk.week_name(w)} --run` 으로 근거를 모은다",
              file=sys.stderr)
        return 2
    names = {c.id: c.name for c in _load_taxonomy(settings).categories}
    # 최신 카드 보관소 — 결정 53(공개 저장소 밖), 자리는 Phase 5 에서 정한다
    store = analyze.CardStore(settings.work_dir / "cards")
    if args.adopt:
        adopted = analyze.adopt_week(settings.data_dir, settings.work_dir, w, store)
        print(dumps_json({"week": wk.week_name(w), "adopted": adopted, "store": str(store.root)}), end="")
        return 0
    if not args.run:
        est = analyze.dry_run(analyze.CardWriter(MockLLM([]), effort=args.effort, names=names), inputs,
                              store=store, force_new=args.force_new)
        print(dumps_json({"dry_run": True, "week": wk.week_name(w), "cap_usd": args.cap, **est}), end="")
        return 0
    try:
        token = settings.require_github_token()
        key = settings.require_anthropic_key()
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 2
    cache = CachingTransport(UrllibTransport(), settings.work_dir / "cache" / "evidence" / wk.week_name(w),
                             cacheable_response)
    gh = LiveGitHub(token, on_wait=_log_wait, transport=cache)

    def repo_exists(full_name: str) -> bool:
        # 비교 저장소는 실제로 있어야 링크를 허용한다 — 확인하지 못하면(오류 포함) 허용하지 않는다
        try:
            gh.get_repo(full_name)
            return True
        except (GitHubError, GitHubFormatError):
            return False

    meter = meter or BudgetMeter(ClaudeLLM(key), cap_usd=args.cap)
    writer = analyze.CardWriter(meter, effort=args.effort, names=names)
    t0 = time.monotonic()
    stats = analyze.run_analyze(writer, inputs, work_dir=settings.work_dir, week_start=w, names=names,
                                repo_exists=repo_exists, today=date.today(), store=store,
                                force_new=args.force_new, log=lambda m: print(m, flush=True))
    summary = {**stats, "week": wk.week_name(w), "spent_usd": round(meter.spent, 4), "cap_usd": args.cap,
               "calls": meter.calls, "seconds": round(time.monotonic() - t0),
               "fingerprint": writer.fingerprint, "dir": str(analyze.card_dir(settings.work_dir, w))}
    write_json(analyze.card_dir(settings.work_dir, w) / f"run-{date.today().isoformat()}.json",
               {**summary, "ledger": meter.ledger})
    print(dumps_json(summary), end="")
    return 0 if stats["stopped"] is None else 3


def _brief(settings: Settings, args: argparse.Namespace, meter: BudgetMeter | None = None) -> int:
    w = _week_arg(args.week, date.today())
    names = {c.id: c.name for c in _load_taxonomy(settings).categories}
    store = analyze.CardStore(settings.work_dir / "cards")     # 결정 53 — analyze 와 같은 보관소
    try:
        bi = brief.load_input(settings.data_dir, store, w, names=names)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2
    if not args.run:
        est = brief.dry_run(brief.BriefWriter(MockLLM([])), bi)
        print(dumps_json({"dry_run": True, "week": wk.week_name(w), "cap_usd": args.cap, **est}), end="")
        return 0
    try:
        key = settings.require_anthropic_key()
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 2
    meter = meter or BudgetMeter(ClaudeLLM(key), cap_usd=args.cap)
    writer = brief.BriefWriter(meter)
    stats = brief.run_brief(writer, bi, work_dir=settings.work_dir, today=date.today(),
                            log=lambda m: print(m, flush=True))
    print(dumps_json({**stats, "week": wk.week_name(w), "spent_usd": round(meter.spent, 4),
                      "cap_usd": args.cap, "ledger": meter.ledger, "fingerprint": writer.fingerprint}),
          end="")
    return 0 if stats["written"] else 3


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


def _score_blind(settings: Settings, tax: taxonomy.Taxonomy, preds_path: Path, *,
                 notes: list[str]) -> Path | None:
    """블라인드 대 판정 — 전체 · 1차(규칙을 만들 때 본 것) · 2차(처음 보는 것)를 나눠 잰다 (FR-14.1, 결정 50).

    정답은 정답 세트(분류 체계 v2)의 블라인드 행. 정답 세트가 없으면 1차 라벨 파일.
    """
    ev_dir = settings.data_dir / "eval"
    gold_path = ev_dir / "goldset_classify.jsonl"
    preds = evaluate.load_predictions(preds_path)
    if gold_path.exists():
        def labels(**kw: Any) -> dict[int, evaluate.Label]:
            return evaluate.load_labels(gold_path, tax, **kw)

        subsets = [("블라인드 전체", labels(blind_only=True)),
                   ("1차 30 — 규칙을 만들 때 본 것", labels(source_prefix="blind:")),
                   ("2차 30 — 처음 보는 것", labels(source_prefix="blind2:"))]
    elif (ev_dir / "goldset_blind_labels.jsonl").exists():
        gold_path = ev_dir / "goldset_blind_labels.jsonl"
        subsets = [("블라인드 30", evaluate.load_labels(gold_path, tax))]
    else:
        return None
    scored = [(name, evaluate.score(g, {i: preds[i] for i in g if i in preds})) for name, g in subsets if g]
    main_name, main = scored[0]
    md = evaluate.report_md(main, title=f"{main_name} 대 Claude 판정", tax=tax, notes=[
        f"정답: `{gold_path.name}` 의 블라인드 행 — 초안 없이 사용자가 라벨(FR-14.1)", *notes])
    md += "\n## 묶음별\n\n" + evaluate.compare_md(scored)
    return evaluate.write_run(settings.data_dir, f"blind-vs-{preds_path.stem}",
                              {"gold": gold_path.name, "predictions": preds_path.name, **main,
                               "by_subset": {n: {k: v for k, v in r.items() if k != "disagreements"}
                                             for n, r in scored}}, md)


def _goldset_draft(settings: Settings, args: argparse.Namespace) -> int:
    ev_dir = settings.data_dir / "eval"
    cand_path = ev_dir / "goldset_candidates.jsonl"
    if not cand_path.exists():
        print(f"후보 파일이 없다 — 먼저 goldset: {cand_path}", file=sys.stderr)
        return 2
    candidates = list(read_jsonl(cand_path))
    more = ev_dir / "goldset_blind2_candidates.jsonl"      # 블라인드 2차(결정 50)
    if more.exists():
        candidates += list(read_jsonl(more))
    if args.blind_only:
        candidates = [c for c in candidates if c.get("blind")]
    tax = _load_taxonomy(settings)
    out = ev_dir / f"{args.out}.jsonl"
    if not args.run:
        est = evaluate.dry_run(n_items=len(candidates), system_prompt=LLMDecider(MockLLM([]), tax).system,
                               batch=not args.no_batch)
        print(dumps_json({"dry_run": True, "candidates": len(candidates),
                          "blind": sum(1 for c in candidates if c.get("blind")),
                          "github_calls": 2 * len(candidates), "cap_usd": args.cap, "out": str(out), **est}),
              end="")
        return 0
    if out.exists():  # 돈을 내고 만든 판정 — 덮어쓰지 않는다
        print(f"이미 있다 — 덮어쓰지 않는다: {out} (--out 으로 다른 이름을 준다)", file=sys.stderr)
        return 2
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
        return run_batch(meter, batch_client, reqs, state=states / f"{args.out}-{tag}.json",
                         poll_seconds=args.poll, log=log)

    t0 = time.monotonic()
    stats = goldset.run_draft(gh, decider, candidates, out=out, batch=None if args.no_batch else runner,
                              log=log)
    seconds = time.monotonic() - t0
    report = None
    if out.exists() and stats["decided"]:   # 이번 실행에서 판정한 것이 없으면 기록하지 않는다
        how = "일반 호출" if args.no_batch else "Batch"
        report = _score_blind(settings, tax, out, notes=[
            f"판정: Claude `{out.name}` · 판정기 `{decider.fingerprint}`",
            f"이번 실행 비용 ${meter.spent:.2f} (후보 {len(candidates)}개, {how})"])
    summary = {**stats, "spent_usd": round(meter.spent, 4), "calls": meter.calls,
               "batch_calls": sum(1 for e in meter.ledger if e["batch"]), "seconds": round(seconds),
               "out": str(out), "blind_report": str(report) if report else None}
    write_json(settings.work_dir / "goldset-draft" / f"{date.today().isoformat()}.json",
               {**summary, "ledger": meter.ledger})
    print(dumps_json(summary), end="")
    return 0 if stats["stopped"] is None else 3


# --- weekly (FR-11) ---

def _ns(**kw: Any) -> argparse.Namespace:
    return argparse.Namespace(**kw)


def _weekly_steps(settings: Settings, args: argparse.Namespace, w: date, *,
                  token: str = "", meter: BudgetMeter | None = None) -> list[weekly.Step]:
    """주간 실행 순서(FR-11.1, PLAN 1-1). 단계 함수는 CLI 의 것을 그대로 부른다 — 따로 쓰는 명령과 같은 길."""
    name = wk.week_name(w)
    today = date.today()
    cap = args.cap

    def contract_step() -> int:
        report = contract.check_github(LiveGitHub(token), today=today)
        print(dumps_json(report.to_dict()), end="")
        return 0 if report.ok else 1

    def discover_step() -> int:
        if w != _last_full_week(today):   # Search 는 지금 스타 수만 준다 — 지난 주들은 찍을 수 없다
            print(f"discover 는 막 끝난 주만 찍을 수 있다 — {name} 스냅샷이 없다", file=sys.stderr)
            return 2
        return _discover(settings, token, _ns(pool_min=1000, new_days=30, new_min=10))

    def rank_step() -> int:
        return _rank(settings, token, _ns(week=name, all=False))

    def check_step() -> int:
        return _analyze(settings, _ns(week=name, check=True))

    def export_step() -> int:
        stats = export.run_export(data_dir=settings.data_dir, work_dir=settings.work_dir,
                                  log=lambda m: print(m, flush=True))
        print(dumps_json(stats), end="")
        return 0

    return [
        weekly.Step("contract", contract_step,
                    what="GitHub API 계약 점검 — 실패하면 아무것도 쓰지 않는다(FR-11.6)"),
        weekly.Step("discover", discover_step, done=lambda: _snapshot_path(settings, w).exists(),
                    what="스타 ≥1,000 전체 + 새 저장소 스냅샷"),
        weekly.Step("stars", lambda: _stars(settings, token, _ns(week=name)),
                    done=lambda: weekfile.week_path(settings.data_dir, w).exists(),
                    what="스냅샷 차이 + 상위 후보 히스토리 → 주간 스타 파일(불변)"),
        weekly.Step("rank", rank_step, what="4축 랭킹 — 전체 탭(판정 전 AI 탭은 비어 있다)"),
        weekly.Step("classify", lambda: _classify(settings, _ns(
            week=name, all=False, run=True, cap=cap, chunk=400, poll=args.poll, no_batch=False), meter=meter),
            llm=True, critical=False, what="랭킹 후보 AI 판정(Batch) — 이미 판정한 것은 다시 하지 않는다"),
        weekly.Step("rank-ai", rank_step, critical=False, what="판정 결과로 AI 탭 채움"),
        weekly.Step("trends", lambda: _trends(settings, _ns(week=name, all=False)), critical=False,
                    what="카테고리 추이(+ALL)"),
        weekly.Step("evidence", lambda: _evidence(settings, _ns(
            week=name, repos=None, run=True, no_web=args.no_web, only_missing=True)),
            critical=False,
            what="AI 탭 저장소 근거 수집(무료 API · Tavily 무료 크레딧) — 모은 저장소는 건너뛴다"),
        weekly.Step("analyze", lambda: _analyze(settings, _ns(
            week=name, repos=None, run=True, cap=cap, effort=analyze.EFFORT, check=False, adopt=False,
            force_new=False), meter=meter),
            llm=True, critical=False, what="심층 카드 — 새 저장소만 LLM, 다시 등장하면 변경 기록(비용 0)"),
        weekly.Step("check", check_step, critical=False, what="카드 품질 검사(호출 0, FR-14.4)"),
        weekly.Step("brief", lambda: _brief(settings, _ns(week=name, run=True, cap=cap), meter=meter),
                    done=lambda: (settings.work_dir / name / "briefing.md").exists(),
                    llm=True, critical=False, what="주간 브리핑 1회 호출"),
        weekly.Step("export", export_step, critical=False,
                    what="사이트 파생 데이터 + 비공개 카드·브리핑 사본"),
        weekly.Step("archive", lambda: _archive(settings, _ns(week=name, secrets=args.secrets)),
                    critical=False,
                    what="압축본(근거 원문 + LLM 로그 · 스냅샷) — 시크릿 검사, 올리기는 워크플로"),
    ]


def _weekly_estimates(settings: Settings, w: date, *, no_web: bool) -> dict[str, dict[str, Any]]:
    """dry-run 추정(호출 0). 입력이 이미 있는 단계는 그 단계의 dry-run, 없으면 실측 기준값(MEASURE)."""
    name = wk.week_name(w)
    out: dict[str, dict[str, Any]] = {
        "discover": {"github_calls": "약 1,170회 · 약 1시간 (MEASURE §12)"},
        "stars": {"github_calls": "상위 후보 히스토리 약 2,000~3,000회 (MEASURE §2)"},
    }
    tax = _load_taxonomy(settings)
    if (settings.data_dir / "weekly" / name / "rankings.json").exists():
        system = LLMDecider(MockLLM([]), tax).system
        c = classify.dry_run(data_dir=settings.data_dir, weeks=[w], system_prompt=system)
        # 첫 묶음이 0 이면 판정할 것이 없다 — 상한(풀 전체)은 첫 묶음 뒤 재질문이 이어질 때만 의미가 있다
        usd = [0.0, 0.0]
        if c["first_round"]:
            usd = [round(c["first_round_usd"][0], 4), round(c["upper_usd"][1], 4)]
        out["classify"] = {"llm_calls": c["first_round"], "usd": usd}
        targets = evidence.targets_for(settings.data_dir, w)
        have = set(evidence.read(settings.work_dir, w))
        todo = [t for t in targets if t.repo_id not in have]
        queries = 0 if no_web else 3
        ev = evidence.plan(todo, web_queries=queries)
        out["evidence"] = {"targets": ev["targets"], "tavily_credits": ev["tavily_credits"],
                           "github_calls_max": ev["github_calls_max"]}
        names = {c2.id: c2.name for c2 in tax.categories}
        store = analyze.CardStore(settings.work_dir / "cards")
        inputs = analyze.load_inputs(settings.data_dir, settings.work_dir, w) if have else []
        if inputs:
            a = analyze.dry_run(analyze.CardWriter(MockLLM([]), effort=analyze.EFFORT, names=names), inputs,
                                store=store)
            out["analyze"] = {"llm_calls": a["llm_calls"], "usd": a["total_usd"]}
        try:
            bi = brief.load_input(settings.data_dir, store, w, names=names)
            b = brief.dry_run(brief.BriefWriter(MockLLM([])), bi)
            out["brief"] = {"llm_calls": b["llm_calls"], "usd": b["total_usd"]}
        except FileNotFoundError:
            pass
    for step in ("classify", "analyze", "brief", "evidence"):
        out.setdefault(step, {"note": "앞 단계 뒤에 정해진다 — LLM 은 전체 상한 안에서만"})
    return out


def _weekly(settings: Settings, args: argparse.Namespace) -> int:
    today = date.today()
    w = _week_arg(args.week, today)
    name = wk.week_name(w)
    if not args.run:
        steps = _weekly_steps(settings, args, w)
        plan = weekly.plan_weekly(steps, estimates=_weekly_estimates(settings, w, no_web=args.no_web))
        print(dumps_json({"dry_run": True, "week": name, "cap_usd": args.cap, **plan,
                          "note": "usd 는 추정이 있는 단계만의 합 — 실제 LLM 지출은 cap_usd 안(FR-11.2)"}),
              end="")
        return 0
    try:
        token = settings.require_github_token()
        key = settings.require_anthropic_key()
        if not args.no_web:
            settings.require_tavily_key()
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 2
    meter = BudgetMeter(ClaudeLLM(key), cap_usd=args.cap)
    started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    steps = _weekly_steps(settings, args, w, token=token, meter=meter)
    result = weekly.run_weekly(steps, spent=lambda: meter.spent, log=lambda m: print(m, flush=True))
    extra = {"cap_usd": args.cap, "llm_calls": meter.calls}
    # 계약 점검이 실패하면 정본(data/)에 아무것도 쓰지 않는다(FR-11.6) — 기록은 작업 폴더에만
    contract_failed = result["steps"][0]["status"] == "failed"
    where = settings.work_dir if contract_failed else settings.data_dir
    weekly.write_record(weekly.record_path(where, name), name, result, started=started, extra=extra)
    write_json(settings.work_dir / name / f"weekly-ledger-{today.isoformat()}.json", {"ledger": meter.ledger})
    print(dumps_json({"week": name, **extra, **result}), end="")
    return {"ok": 0, "stopped": 3}.get(result["status"], 1)


# --- archive · private (FR-10·11.8, 결정 55) ---

def _archive(settings: Settings, args: argparse.Namespace) -> int:
    name = wk.week_name(_week_arg(args.week, date.today()))
    try:
        out = archive.build(settings.work_dir, name, secrets=args.secrets)
    except (archive.SecretFound, archive.ArchiveTooLarge) as e:
        print(e, file=sys.stderr)
        return 1
    print(dumps_json(out), end="")
    return 0


def _private(settings: Settings, args: argparse.Namespace) -> int:
    target = Path(args.pull or args.push)
    if not target.is_dir():
        print(f"비공개 저장소 체크아웃이 없다: {target}", file=sys.stderr)
        return 2
    if args.pull:
        stats = private.pull(target, settings.work_dir)
    else:
        stats = private.push(settings.work_dir, target)
    print(dumps_json({"direction": "pull" if args.pull else "push", "dir": str(target), **stats}), end="")
    return 0


# --- notion (FR-15, 결정 34·38·59) ---

def _notion_index(settings: Settings) -> Path:
    return settings.work_dir / "notion" / "index.json"     # 결정 59 — 공개 저장소에 올리지 않는다


def _notion_setup(settings: Settings, args: argparse.Namespace) -> int:
    path = _notion_index(settings)
    idx = notion.load_index(path)
    site = read_json(settings.data_dir / "site" / "index.json")
    names = {c["id"]: c["name"] for c in site.get("categories", [])}
    types = list(site.get("types", []))
    titles = [t for t, _ in notion.schemas(names, types).values()]
    if not args.run:
        print(dumps_json({"dry_run": True, "parent": args.parent, "databases": titles,
                          "set_up": bool(idx["databases"]), "index": str(path)}), end="")
        return 0
    try:
        token = settings.require_notion_token()
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 2
    try:
        notion.setup(LiveNotion(token), args.parent, idx, names=names, types=types)
    except notion.NotionStageError as e:
        print(e, file=sys.stderr)
        return 1
    finally:
        if idx["databases"]:          # 중간에 멈춰도 만든 DB 는 기록한다 — 같은 DB 를 둘 만들지 않게
            notion.save_index(path, idx)
    print(dumps_json({"dry_run": False, "databases": idx["databases"], "index": str(path)}), end="")
    return 0


def _notion(settings: Settings, args: argparse.Namespace) -> int:
    name = wk.week_name(_week_arg(args.week, date.today()))
    path = _notion_index(settings)
    idx = notion.load_index(path)
    try:
        wd = notion.load_week(settings.data_dir / "site", settings.work_dir / "site-private", name)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2
    post = _blog_post(settings, name)
    if not args.run:
        p = notion.plan(idx, wd)
        if post:
            p["create"] += name not in (idx.get("blog") or {})
            p["pages"] += 1
        print(dumps_json({"dry_run": True, **p, "blog": post[0] if post else None}), end="")
        return 0
    try:
        token = settings.require_notion_token()
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 2
    client = LiveNotion(token)

    def save(i: dict[str, Any]) -> None:
        notion.save_index(path, i)

    log = lambda m: print(m, flush=True)  # noqa: E731
    try:
        stats = notion.publish_week(client, idx, wd, save=save, log=log)
        if post:
            b = notion.publish_blog(client, idx, name, post[0], post[1], save=save, log=log)
            stats = {k: stats[k] + b[k] for k in stats}
    except notion.NotionStageError as e:
        print(e, file=sys.stderr)
        return 1
    notion.save_index(path, idx)
    print(dumps_json({"dry_run": False, "week": name, **stats, "blog": post[0] if post else None,
                      "requests": client.calls}), end="")
    return 0


# --- blog (FR-16, 결정 36·37·39·59) ---

def _blog_post(settings: Settings, name: str) -> tuple[str, str] | None:
    """`.work/<주>/blog/post.md` → (제목, 본문). 첫 줄이 `# 제목`."""
    p = settings.work_dir / name / "blog" / "post.md"
    if not p.exists():
        return None
    head, _, body = p.read_text(encoding="utf-8").partition("\n")
    return head.removeprefix("# ").strip(), body.lstrip("\n")


def _published_posts(settings: Settings, current: str) -> list[tuple[int, str, str]]:
    """글 모음(FR-16.8) — 블로그 초안 DB 에서 상태가 '게시됨'이고 네이버 주소가 있는 글.

    토큰이 없으면 빈 목록.
    """
    idx = notion.load_index(_notion_index(settings))
    others = {w: v for w, v in (idx.get("blog") or {}).items() if w != current}
    if not others or not settings.notion_token:
        return []
    client = LiveNotion(settings.notion_token)
    out: list[tuple[int, str, str]] = []
    for w, ref in sorted(others.items()):
        try:
            page = client.get_page(ref["page_id"])
        except NotionError as e:
            print(f"  글 모음: {w} 페이지를 읽지 못했다 — {e}", flush=True)
            continue
        url = (page.properties.get("네이버 글 주소") or {}).get("url")
        title = "".join(t.get("plain_text", "") for t in (page.properties.get("제목") or {}).get("title", []))
        if notion_status(page, notion.STATUS) == "게시됨" and isinstance(url, str) and url:
            out.append((blog.episode(w), title.split(blog.EMOJI)[-1].strip() or title, url))
    return out


def _blog_images(settings: Settings, bi: blog.BlogInput) -> tuple[dict[str, str], dict[str, str]]:
    """대표 이미지(결정 60) — 주인이 올린 소셜 미리보기를 찾아 `.work/<주>/blog/img/` 에 받는다(비용 0).

    (저장소 → 그림 URL, 저장소 → 받은 파일 경로). 토큰이 없거나 실패하면 빈 채로 — 생성 프롬프트가 맡는다.
    """
    if not settings.github_token:
        print("  대표 이미지: GITHUB_TOKEN 없음 — 생성 프롬프트만", flush=True)
        return {}, {}
    try:
        found = repo_images.social_previews([r.full_name for r in bi.repos], settings.github_token)
    except (repo_images.RepoImageError, TransportError) as e:
        print(f"  대표 이미지: 찾지 못했다 — {e}", flush=True)
        return {}, {}
    images: dict[str, str] = {}
    files: dict[str, str] = {}
    out = settings.work_dir / bi.week / "blog" / "img"
    for name, url in found.items():
        try:
            data, ext = repo_images.download(url)
        except (repo_images.RepoImageError, TransportError) as e:
            print(f"  대표 이미지: {name} 받지 못했다 — {e}", flush=True)
            continue
        out.mkdir(parents=True, exist_ok=True)
        rel = f"img/{name.replace('/', '__')}{ext}"
        (out.parent / rel).write_bytes(data)
        images[name], files[name] = url, rel
    print(f"  대표 이미지: TOP {len(bi.repos)} 중 {len(images)}개(소셜 미리보기) — 나머지는 생성 프롬프트",
          flush=True)
    return images, files


def _blog(settings: Settings, args: argparse.Namespace) -> int:
    name = wk.week_name(_week_arg(args.week, date.today()))
    try:
        bi = blog.load_input(settings.data_dir / "site", settings.work_dir / "site-private", name)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2
    if not args.run:
        est = blog.dry_run(blog.BlogWriter(MockLLM([])), bi)
        print(dumps_json({"dry_run": True, "week": name, "cap_usd": args.cap, **est}), end="")
        return 0
    try:
        key = settings.require_anthropic_key()
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 2
    images, files = _blog_images(settings, bi)
    meter = BudgetMeter(ClaudeLLM(key), cap_usd=args.cap)
    writer = blog.BlogWriter(meter)
    stats = blog.run_blog(writer, bi, work_dir=settings.work_dir, today=date.today(),
                          published=_published_posts(settings, name), images=images, files=files,
                          log=lambda m: print(m, flush=True))
    print(dumps_json({**stats, "week": name, "spent_usd": round(meter.spent, 4), "cap_usd": args.cap,
                      "ledger": meter.ledger, "fingerprint": writer.fingerprint}), end="")
    return 0 if stats["written"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
