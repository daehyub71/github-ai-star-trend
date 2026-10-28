"""근거 수집 (SPEC FR-5.6·5.7·5.8). 비용 0 — 출처는 무료 API 와 무료 한도 검색만 쓴다.

출처를 정해진 순서(GitHub → HN → 웹 …)로 부르고 URL 로 중복을 없앤다. 앞 출처가 우선이다.
한 출처가 실패해도 멈추지 않고 실패를 기록한다 — 카드에 "수집 실패"로 남기기 위함이다(FR-5.7).
예산 초과만은 그대로 올려 보낸다(FR-11.2 — 근거 거르기가 LLM 을 쓰게 되면 해당).

목록은 `.work/<주>/evidence.jsonl`(저장소마다 한 줄), 원문은 `.work/<주>/raw/<해시>.txt`.
정본(data/)에는 URL·해시·짧은 인용만 간다(FR-5.8) — 그것은 analyze 가 카드에 남긴다.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from startrend.budget import BudgetExceeded
from startrend.clients.evidence.base import EvidenceSource, Target
from startrend.core import evidence as ev
from startrend.core import io, spikes, week, weekfile

ERROR_CHARS = 300


@dataclass
class Collected:
    target: Target
    docs: list[ev.Evidence]
    failures: list[dict[str, str]] = field(default_factory=list)   # {"source", "error"}

    @property
    def failed_sources(self) -> list[str]:
        return [f["source"] for f in self.failures]

    @property
    def urls(self) -> list[str]:
        """인용 게이트에 넘길 근거 URL (FR-7.2)."""
        return [d.url for d in self.docs]


def gather(target: Target, sources: Sequence[EvidenceSource], *,
           log: Callable[[str], None] = print) -> Collected:
    docs: list[ev.Evidence] = []
    failures: list[dict[str, str]] = []
    for s in sources:
        try:
            got = s.collect(target)
        except BudgetExceeded:
            raise
        except Exception as e:          # FR-5.7 — 어떤 실패든 이 출처만 건너뛴다
            msg = f"{type(e).__name__}: {e}"[:ERROR_CHARS]
            failures.append({"source": s.name, "error": msg})
            log(f"  {target.full_name}: {s.name} 수집 실패 — {msg}")
            continue
        docs.extend(got)
    return Collected(target, ev.dedupe(docs), failures)


AXIS_ORDER = ("gain", "fresh", "growth", "total")
SPIKE_WEEKS = 5            # 이번 주 포함 앞 5주의 일별 곡선에서 급등일을 찾는다 (앞 14일 기준선 + 이번 주)
GITHUB_CALLS_PER_REPO = 7  # 저장소·README·릴리스·기여자 2·이슈 검색 2 (P3-2 실측)
HN_CALLS_PER_REPO = 2
GEEKNEWS_REQUESTS = (7, 21)  # 7일 × 1~3쪽 — 주에 한 번 훑는다


def targets_for(data_dir: Path, week_start: date, *, repos: Sequence[str] | None = None) -> list[Target]:
    """그 주 AI 탭(4축)의 서로 다른 저장소 — 축 순서·순위 순. repos 가 있으면 그것만(대소문자 무시).

    급등일(focus)은 주간 파일의 정밀 일별 값으로 찾는다(FR-6.3) — HN 근거를 그 날 가까운 것부터
    고르는 데 쓴다.
    """
    ranking = week_dir_data(data_dir, week_start) / "rankings.json"
    if not ranking.exists():
        raise FileNotFoundError(f"랭킹이 없다: {ranking}")
    axes = io.read_json(ranking).get("axes") or {}
    want = {r.lower() for r in repos} if repos else None
    seen: dict[int, dict[str, Any]] = {}
    for a in AXIS_ORDER:
        for e in (axes.get(a) or {}).get("ai") or []:
            if e["id"] not in seen and (want is None or e["full_name"].lower() in want):
                seen[e["id"]] = e
    rows = {w: weekfile.read(p) for k in range(SPIKE_WEEKS)
            if (p := weekfile.week_path(data_dir, w := week_start - timedelta(days=7 * k))).exists()}
    out = []
    until = week.week_end(week_start)
    for rid, e in seen.items():
        daily = spikes.daily_from_weeks({w: r[rid] for w, r in rows.items() if rid in r})
        created = date.fromisoformat(e["created"]) if e.get("created") else None
        focus = spikes.focus_days(spikes.find_spikes(daily, created=created))
        out.append(Target(rid, e["full_name"], since=week_start, until=until, focus=focus))
    return out


def plan(targets: Sequence[Target], *, web_queries: int = 3) -> dict[str, Any]:
    """호출 0 — 대상 수와 출처별 요청 수. 근거 수집은 무료 API·무료 한도 검색만 쓴다(비용 0)."""
    n = len(targets)
    return {"targets": n, "repos": [t.full_name for t in targets],
            "github_calls_max": GITHUB_CALLS_PER_REPO * n, "hn_calls": HN_CALLS_PER_REPO * n,
            "geeknews_requests": list(GEEKNEWS_REQUESTS), "tavily_credits": web_queries * n,
            "package_calls": "저장소당 이름 후보 2~5회 + 다운로드 0~2회", "cost_usd": 0}


def run_evidence(sources: Sequence[EvidenceSource], targets: Sequence[Target], *, work_dir: Path,
                 week_start: date, log: Callable[[str], None] = print) -> dict[str, Any]:
    """대상마다 근거를 모아 그 주 목록에 합친다(앞서 모은 다른 저장소는 남긴다)."""
    merged = read(work_dir, week_start)
    by_source: dict[str, int] = {}
    failures = 0
    for i, t in enumerate(targets, 1):
        c = gather(t, sources, log=log)
        merged[t.repo_id] = c
        for d in c.docs:
            by_source[d.source] = by_source.get(d.source, 0) + 1
        failures += len(c.failures)
        log(f"  [{i}/{len(targets)}] {t.full_name}: 근거 {len(c.docs)}건"
            + (f" · 수집 실패 {', '.join(c.failed_sources)}" if c.failures else ""))
    write(work_dir, week_start, list(merged.values()))
    return {"targets": len(targets), "docs": sum(by_source.values()), "by_source": by_source,
            "failures": failures}


def week_dir_data(data_dir: Path, week_start: date) -> Path:
    return data_dir / "weekly" / week.week_name(week_start)


def week_dir(work_dir: Path, week_start: date) -> Path:
    return work_dir / week.week_name(week_start)


def evidence_path(work_dir: Path, week_start: date) -> Path:
    return week_dir(work_dir, week_start) / "evidence.jsonl"


def _row(c: Collected) -> dict[str, Any]:
    t = c.target
    return {"repo_id": t.repo_id, "full_name": t.full_name, "since": t.since.isoformat(),
            "until": t.until.isoformat(), "focus": [d.isoformat() for d in t.focus],
            "docs": [d.record() for d in c.docs], "failures": c.failures}


def write(work_dir: Path, week_start: date, collected: Sequence[Collected]) -> Path:
    """목록을 쓰고 원문을 해시 이름으로 남긴다(같은 해시는 다시 쓰지 않는다)."""
    raw = week_dir(work_dir, week_start) / "raw"
    for c in collected:
        for d in c.docs:
            p = raw / f"{d.content_hash}.txt"
            if d.text and not p.exists():
                io.write_text_atomic(p, d.text)
    path = evidence_path(work_dir, week_start)
    io.write_jsonl(path, [_row(c) for c in sorted(collected, key=lambda c: c.target.repo_id)])
    return path


def read(work_dir: Path, week_start: date) -> dict[int, Collected]:
    path = evidence_path(work_dir, week_start)
    out: dict[int, Collected] = {}
    if not path.exists():
        return out
    for row in io.read_jsonl(path):
        t = Target(int(row["repo_id"]), row["full_name"], since=date.fromisoformat(row["since"]),
                   until=date.fromisoformat(row["until"]),
                   focus=tuple(date.fromisoformat(x) for x in row.get("focus") or ()))
        docs = [ev.from_record(r) for r in row["docs"]]
        out[t.repo_id] = Collected(t, docs, list(row.get("failures") or []))
    return out
