"""실측 (SPEC FR-12, 비용 0). Phase 0 의 첫 산출물은 코드가 아니라 이 숫자들이다.

재는 것
- 후보 규모: 스타 기준별 저장소 수, 새 저장소 수, Search 로 열거할 때의 호출 수 (FR-12.1)
- 히스토리 API: 레이트 리밋 풀, 호출 수·시간 (FR-12.2)
- 주간 증가량·성장률 분포: 스타 규모 구간별 표본 → 기준 이상 저장소 수 추정 (FR-12.3 → D-3)
- Trending 대조: 우리 후보 규칙이 Trending 주간 목록을 얼마나 포함하는가 (FR-12.1 → D-2)
- 분류 규모: README 길이·토큰 추정, AI 키워드 비율 대략치 (FR-12.4·12.6)
- 주 경계: API 주의 시간대, 진행 중인 주가 응답에 들어오는지 (FR-12.7)

표본의 한계: 구간 안에서 스타 값을 고르게 뽑으므로 구간 위쪽이 실제 분포보다 많이 뽑힌다.
구간을 잘게 나눠 이 치우침을 줄였지만, 추정치는 크기 순서를 보는 용도다.
"""

import json
import math
import random
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from startrend.clients.github import SEARCH_RESULT_CAP, GitHubClient, GitHubError
from startrend.clients.github_parse import GitHubFormatError
from startrend.clients.trending import parse_trending, trending_url
from startrend.core import io, week
from startrend.core.models import HistoryWeek, Repo

Bucket = tuple[int, int | None]  # (최소 스타, 최대 스타 — None 이면 상한 없음)

POOL_THRESHOLDS = [50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000]
NEW_DAYS = [7, 30]
NEW_MIN_STARS = [10, 50, 100, 500]
BUCKETS: list[Bucket] = [
    (100, 199), (200, 499), (500, 999), (1000, 1999), (2000, 4999),
    (5000, 9999), (10000, 19999), (20000, 49999), (50000, None),
]
GAIN_THRESHOLDS = [10, 50, 100, 500, 1000, 5000]
COVERAGE_THRESHOLDS = [100, 500, 1000, 2000, 5000]
README_HEAD_CHARS = 4000  # 분류 입력으로 넣을 README 앞부분 (가정 — Phase 2 에서 조정)

_AI_WORDS = re.compile(
    r"\b(ai|llms?|gpts?|agents?|agentic|mcp|rag|chatbots?|copilot|claude|openai|gemini|ollama|"
    r"transformers?|diffusion|embeddings?|prompts?|inference|fine-?tun\w*|neural|deep[- ]learning|"
    r"machine[- ]learning|ml|nlp|vlm|multimodal|langchain|llama|mistral|qwen|deepseek)\b",
    re.I,
)
_AI_TOPICS = {"ai", "llm", "llms", "agents", "ai-agents", "mcp", "rag", "machine-learning", "deep-learning",
              "generative-ai", "chatgpt", "openai", "claude", "gpt", "langchain", "llama", "ollama",
              "model-context-protocol", "ai-agent", "agent", "artificial-intelligence", "nlp"}


@dataclass(frozen=True)
class WeekStats:
    last_full_week: date
    last_full_gain: int
    partial: int  # 진행 중인 주의 지금까지 값 (API 가 주지 않으면 0)
    mean4: float  # 최근 완결된 4주 평균
    start_stars: int  # 지난 주 시작 시점 스타 (추정: 현재 − 진행 중 − 지난 주)
    growth: float | None  # 지난 주 증가량 ÷ 시작 시점 스타
    current_week_present: bool


# --- 순수 함수 ---


def week_stats(weeks: list[HistoryWeek], current_total: int, today: date) -> WeekStats:
    cur = week.week_start(today)
    last = cur - timedelta(days=7)
    by_week = {w.week: w.total for w in weeks}
    partial = by_week.get(cur, 0)
    gain = by_week.get(last, 0)
    recent = [by_week.get(last - timedelta(days=7 * i), 0) for i in range(4)]
    start = max(current_total - partial - gain, 0)
    return WeekStats(
        last_full_week=last,
        last_full_gain=gain,
        partial=partial,
        mean4=sum(recent) / 4,
        start_stars=start,
        growth=(gain / start) if start > 0 else None,
        current_week_present=cur in by_week,
    )


def sample_star_values(lo: int, hi: int, n: int, rng: random.Random) -> list[int]:
    span = hi - lo + 1
    return rng.sample(range(lo, hi + 1), min(n, span))


def bucket_query(bucket: Bucket) -> str:
    lo, hi = bucket
    return f"stars:>={lo}" if hi is None else f"stars:{lo}..{hi}"


def bucket_key(bucket: Bucket) -> str:
    lo, hi = bucket
    return f"{lo}+" if hi is None else f"{lo}..{hi}"


def estimate_counts(bucket_counts: Mapping[Bucket, int], bucket_gains: Mapping[Bucket, Sequence[int]],
                    thresholds: Iterable[int]) -> dict[int, float]:
    """구간별 저장소 수 × 표본에서 기준 이상 비율 → 전체에서 기준 이상인 저장소 수 추정."""
    out = {}
    for t in thresholds:
        total = 0.0
        for b, n in bucket_counts.items():
            gains = bucket_gains.get(b) or []
            if gains:
                total += n * sum(g >= t for g in gains) / len(gains)
        out[t] = total
    return out


def percentiles(values: Sequence[float], ps: Iterable[int]) -> dict[int, float | None]:
    xs = sorted(values)
    out: dict[int, float | None] = {}
    for p in ps:
        if not xs:
            out[p] = None
            continue
        k = (len(xs) - 1) * p / 100
        f = math.floor(k)
        c = min(f + 1, len(xs) - 1)
        out[p] = round(xs[f] + (xs[c] - xs[f]) * (k - f), 6)
    return out


def coverage(rows: list[dict[str, Any]], thresholds: Iterable[int], new_days: int,
             today: date) -> dict[int, float]:
    """후보 규칙 '현재 스타 ≥ T 또는 생성 N일 이내' 가 rows 를 얼마나 포함하는가."""
    cutoff = week.week_start(today) - timedelta(days=new_days)
    out = {}
    for t in thresholds:
        hit = sum(
            1 for r in rows
            if r["stars"] >= t or datetime.fromisoformat(r["created_at"]).date() >= cutoff
        )
        out[t] = hit / len(rows) if rows else 0.0
    return out


def estimate_tokens(text: str) -> int:
    """대략치: 영문은 4글자당 1토큰, 그 밖(한글 등)은 1.5글자당 1토큰. 실제 토큰 수는 Phase 2 에서 잰다."""
    ascii_n = sum(1 for ch in text if ch.isascii())
    return round(ascii_n / 4 + (len(text) - ascii_n) / 1.5)


def looks_ai(repo: Repo) -> bool:
    """키워드 대략치 — AI 판정은 Phase 2 에서 LLM 이 한다(결정 19). 비율 추정에만 쓴다."""
    if any(t.lower() in _AI_TOPICS for t in repo.topics):
        return True
    text = f"{repo.full_name.replace('/', ' ').replace('-', ' ')} {repo.description or ''}"
    return bool(_AI_WORDS.search(text))


def enumeration_calls(n_repos: int) -> int:
    """Search 로 n 개를 열거하는 데 드는 쪽 수 (쪽당 100개). 구간 분할 여분은 제외."""
    return math.ceil(n_repos / 100)


def iso(dt: datetime | date) -> str:
    return dt.isoformat()


# --- 실행 ---


def run_probe(
    gh: GitHubClient,
    *,
    fetch_html: Callable[[str], str],
    today: date,
    out_dir: Path,
    samples_per_bucket: int = 20,
    readme_sample: int = 60,
    seed: int = 20261026,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    rng = random.Random(seed)
    started = datetime.now().astimezone()
    rate: dict[str, Any] = {}
    samples: list[dict[str, Any]] = []
    offsets: set[float] = set()
    current_present: list[bool] = []

    def note_rate(endpoint: str) -> None:
        if endpoint not in rate:
            rl = gh.last_rate_limit
            rate[endpoint] = asdict(rl) if rl else None

    def total(query: str) -> int:
        try:
            n = gh.search_repositories(query, per_page=1).total_count
        except (GitHubError, GitHubFormatError) as e:
            log(f"  ! {query}: {e}")
            return -1
        note_rate("search")
        return n

    def history(repo: Repo) -> WeekStats | None:
        try:
            weeks = gh.star_history(repo.full_name)
        except (GitHubError, GitHubFormatError) as e:
            log(f"  ! history {repo.full_name}: {e}")
            return None
        note_rate("history")
        offsets.update(w.utc_offset_hours for w in weeks)
        s = week_stats(weeks, repo.stars, today)
        current_present.append(s.current_week_present)
        return s

    # 1) 후보 규모
    log("1/6 후보 규모")
    pool = {f"stars>={t}": total(f"stars:>={t}") for t in POOL_THRESHOLDS}
    new_repos = {}
    for d in NEW_DAYS:
        since = (today - timedelta(days=d)).isoformat()
        for m in NEW_MIN_STARS:
            new_repos[f"created_{d}d_stars>={m}"] = total(f"created:>={since} stars:>={m}")
    bucket_counts = {b: total(bucket_query(b)) for b in BUCKETS}

    # 2) 구간별 표본 → 주간 증가량
    log("2/6 구간별 표본")
    bucket_gains: dict[Bucket, list[int]] = {}
    bucket_growth: dict[Bucket, list[float]] = {}
    sampled: list[Repo] = []
    for b in BUCKETS:
        n_total = bucket_counts[b]
        repos = _sample_bucket(gh, b, n_total, samples_per_bucket, rng, log)
        gains, growth = [], []
        for r in repos:
            s = history(r)
            if s is None:
                continue
            sampled.append(r)
            gains.append(s.last_full_gain)
            if s.growth is not None:
                growth.append(s.growth)
            samples.append({"kind": "bucket", "bucket": bucket_key(b), **_row(r, s)})
        bucket_gains[b] = gains
        bucket_growth[b] = growth
        log(f"  {bucket_key(b)}: 전체 {n_total}, 표본 {len(gains)}")

    # 3) 새 저장소
    log("3/6 새 저장소")
    since30 = (today - timedelta(days=30)).isoformat()
    new_items: list[Repo] = []
    try:
        new_items = list(gh.search_repositories(f"created:>={since30} stars:>=50", per_page=100).items)
    except (GitHubError, GitHubFormatError) as e:
        log(f"  ! new repos: {e}")
    new_gains = []
    for r in rng.sample(new_items, min(samples_per_bucket, len(new_items))):
        s = history(r)
        if s is not None:
            new_gains.append(s.last_full_gain)
            samples.append({"kind": "new", **_row(r, s)})

    # 4) Trending 대조
    log("4/6 Trending 대조")
    trend_rows: list[dict[str, Any]] = []
    trend_error = None
    try:
        trending = parse_trending(fetch_html(trending_url("weekly")))
    except Exception as e:  # 대조 출처 실패는 실측 전체를 멈추지 않는다
        trending, trend_error = [], str(e)
    for t in trending:
        try:
            repo = gh.get_repo(t.full_name)
        except (GitHubError, GitHubFormatError) as e:
            log(f"  ! trending {t.full_name}: {e}")
            continue
        note_rate("repo")
        s = history(repo)
        row = {**_row(repo, s), "trending_period_stars": t.stars_period}
        trend_rows.append(row)
        samples.append({"kind": "trending", **row})

    # 5) README · 분류 규모
    log("5/6 README 표본")
    readme_chars, head_tokens, missing = [], [], 0
    for r in rng.sample(sampled, min(readme_sample, len(sampled))):
        try:
            text = gh.readme(r.full_name)
        except (GitHubError, GitHubFormatError) as e:
            log(f"  ! readme {r.full_name}: {e}")
            continue
        note_rate("readme")
        if text is None:
            missing += 1
            continue
        readme_chars.append(len(text))
        head_tokens.append(estimate_tokens(text[:README_HEAD_CHARS]))

    # 6) 정리
    log("6/6 정리")
    row_bytes = _row_bytes(samples)
    report: dict[str, Any] = {
        "run": {"today": iso(today), "seed": seed, "samples_per_bucket": samples_per_bucket,
                "started": iso(started), "finished": iso(datetime.now().astimezone())},
        "pool": pool,
        "new_repos": new_repos,
        "buckets": {bucket_key(b): n for b, n in bucket_counts.items()},
        "enumeration_by_search": {
            k: {"repos": n, "search_calls": enumeration_calls(n), "minutes_at_30_per_min":
                round(enumeration_calls(n) / 30, 1)} for k, n in pool.items() if n >= 0
        },
        "history_for_every_repo": {
            k: {"history_calls": n, "hours_at_5000_per_hour": round(n / 5000, 2)}
            for k, n in pool.items() if n >= 0
        },
        "sample": {
            "n": sum(len(g) for g in bucket_gains.values()),
            "by_bucket": {
                bucket_key(b): {
                    "n": len(bucket_gains[b]),
                    "gain": percentiles(bucket_gains[b], [50, 90, 100]),
                    "growth": percentiles(bucket_growth[b], [50, 90, 100]),
                } for b in BUCKETS
            },
            "estimated_repos_with_weekly_gain_at_least": {
                str(t): round(v)
                for t, v in estimate_counts(bucket_counts, bucket_gains, GAIN_THRESHOLDS).items()
            },
            "note": "구간 안에서 스타 값을 고르게 뽑아 구간 위쪽이 많이 뽑힌다 — 크기 순서만 보는 추정치",
        },
        "new_sample": {"n": len(new_gains), "gain": percentiles([float(g) for g in new_gains], [50, 90, 100]),
                       "top_new_repos": [{"full_name": r.full_name, "stars": r.stars,
                                          "created_at": iso(r.created_at)} for r in new_items[:10]]},
        "trending": {
            "rows": len(trend_rows),
            "error": trend_error,
            "min_period_stars": min((r["trending_period_stars"] for r in trend_rows), default=None),
            "coverage": {str(t): round(v, 3) for t, v in
                         coverage(trend_rows, COVERAGE_THRESHOLDS, 30, today).items()},
            "items": trend_rows,
        },
        "readme": {"n": len(readme_chars), "missing": missing,
                   "chars": percentiles([float(c) for c in readme_chars], [50, 90]),
                   "head_tokens_est": percentiles([float(t) for t in head_tokens], [50, 90]),
                   "head_tokens_est_mean": (round(sum(head_tokens) / len(head_tokens))
                                            if head_tokens else None),
                   "head_chars": README_HEAD_CHARS},
        "ai_keyword_ratio": {
            "bucket_sample": _ratio(looks_ai(r) for r in sampled),
            "new_top": _ratio(looks_ai(r) for r in new_items),
            "note": "키워드 대략치 — 확정은 Phase 2 전수 분류",
        },
        "week_boundary": {
            "utc_offset_hours": sorted(offsets),
            "current_week_present": bool(current_present) and all(current_present),
            "current_week": iso(week.week_start(today)),
        },
        "rate_limits": rate,
        "calls": dict(Counter(gh.stats.calls)),
        "data_growth": {
            "csv_row_bytes_est": row_bytes,
            **{k: {"weekly_csv_bytes": n * row_bytes} for k, n in pool.items() if n >= 0},
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    io.write_json(out_dir / "report.json", report)
    io.write_jsonl(out_dir / "samples.jsonl", samples)
    return report


def _sample_bucket(gh: GitHubClient, bucket: Bucket, n_total: int, n: int,
                   rng: random.Random, log: Callable[[str], None]) -> list[Repo]:
    if n_total <= 0:
        return []
    q = bucket_query(bucket)
    try:
        if n_total <= SEARCH_RESULT_CAP:  # 구간 전체를 받을 수 있다 — 고르게 뽑는다
            pool: list[Repo] = []
            for page in range(1, math.ceil(n_total / 100) + 1):
                pool.extend(gh.search_repositories(q, page=page, per_page=100).items)
            return rng.sample(pool, min(n, len(pool)))
        lo, hi = bucket
        hi = hi if hi is not None else lo * 10
        # 구간 밀도에 맞춰 창 폭을 정한다 — 창마다 평균 5개쯤 걸리게
        window = max(1, math.ceil((hi - lo + 1) / n_total * 5))
        out: list[Repo] = []
        seen: set[int] = set()
        for s in sample_star_values(lo, max(lo, hi - window + 1), n * 2, rng):
            if len(out) >= n:
                break
            items = gh.search_repositories(f"stars:{s}..{s + window - 1}", per_page=20).items
            if items:
                r = rng.choice(items)
                if r.id not in seen:
                    seen.add(r.id)
                    out.append(r)
        return out
    except (GitHubError, GitHubFormatError) as e:
        log(f"  ! sample {q}: {e}")
        return []


def _row(repo: Repo, s: WeekStats | None) -> dict[str, Any]:
    d: dict[str, Any] = {"id": repo.id, "full_name": repo.full_name, "stars": repo.stars,
                         "created_at": iso(repo.created_at), "language": repo.language,
                         "looks_ai": looks_ai(repo)}
    if s is not None:
        d.update({"last_full_gain": s.last_full_gain, "partial": s.partial, "mean4": s.mean4,
                  "start_stars": s.start_stars, "growth": s.growth})
    return d


def _row_bytes(samples: list[dict[str, Any]]) -> int:
    """주간 CSV 한 줄(저장소 ID, 총 스타, 주간 증가, 요일 7개)의 평균 바이트 — 대략치."""
    lens = [len(f"{s['id']},{s['stars']},{s.get('last_full_gain', 0)},0,0,0,0,0,0,0\n") for s in samples]
    return round(sum(lens) / len(lens)) if lens else 40


def _ratio(flags: Iterable[bool]) -> float | None:
    xs = list(flags)
    return round(sum(xs) / len(xs), 3) if xs else None


def load_report(path: Path) -> dict[str, Any]:
    return dict(json.loads(io.read_text(path)))
