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
"""

import argparse
import base64
import io as _stdio
import json
import sys
from collections.abc import Mapping
from datetime import date, timedelta
from pathlib import Path

from startrend.clients.github_live import LiveGitHub, cacheable_response
from startrend.clients.github_parse import GitHubFormatError, parse_repo, parse_search_page
from startrend.clients.transport import CachingTransport, UrllibTransport
from startrend.clients.trending import fetch_trending
from startrend.core import snapshot, weekfile
from startrend.core import week as wk
from startrend.core.config import ConfigError, Settings, load_settings
from startrend.core.io import dumps_json, read_json, write_json, write_jsonl
from startrend.core.models import Repo
from startrend.stages import backfill, contract, discover, goldset, probe, rank, stars


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
    args = ap.parse_args(argv)

    settings = load_settings(env=env)
    if args.cmd == "goldset":  # 네트워크를 쓰지 않는다 — 토큰 없이 돈다
        return _goldset(settings, args)
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


def _probe(settings: Settings, token: str, args: argparse.Namespace) -> int:
    today = date.today()
    out = settings.work_dir / "probe" / today.isoformat()
    cache = CachingTransport(UrllibTransport(), settings.work_dir / "probe" / "cache", cacheable_response)
    gh = LiveGitHub(token, transport=cache)
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
    gh = LiveGitHub(token, transport=cache)
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
    gh = LiveGitHub(token, transport=cache)
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
    gh = LiveGitHub(token, transport=cache, max_rate_wait=3700.0, max_rate_waits=100)
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
    gh = LiveGitHub(token, transport=cache)
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
                              log=lambda m: print(m, flush=True))
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
    picks = goldset.sample(repos, ranked=ranked, new=new, seed=args.seed)
    out = settings.data_dir / "eval" / "goldset_candidates.jsonl"
    write_jsonl(out, picks)
    groups: dict[str, int] = {}
    for p in picks:
        groups[p["group"]] = groups.get(p["group"], 0) + 1
    print(dumps_json({"snapshot": len(snap), "with_meta": len(repos), "ranked_pool": len(ranked & set(repos)),
                      "picked": len(picks), "groups": groups, "blind": sum(p["blind"] for p in picks),
                      "out": str(out)}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
