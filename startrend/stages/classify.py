"""분류 (SPEC FR-3.1·3.5·3.6, 결정 19·30·45). 과금 단계 — dry-run 이 먼저다(NFR-2).

판정 범위는 **랭킹 후보만**이다. rank 가 남긴 축별 후보 순서(rankings.json 의 pool)를 위에서부터 내려가며,
축마다 AI 저장소 15개가 찰 때까지만 판정한다. 결과가 나와야 다음에 판정할 곳을 알 수 있으므로 묶음(round)으로
나눈다 — 모자란 AI 수 ÷ 예상 AI 비율만큼 미판정 저장소를 한 번에 판정하고, 다 찰 때까지 되풀이한다.

판정 입력(설명·토픽·언어·README 앞부분)과 판정기 지문(프롬프트·모델·effort)의 해시가 지난번과 같으면
다시 판정하지 않는다(FR-3.5). 결과는 저장소 meta.json 의 "classify" 에 남긴다.
예산 상한에 걸리면 그때까지 판정한 것은 남기고 멈춘다(FR-11.2).
"""

from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from startrend.budget import BudgetExceeded
from startrend.clients.decision import (
    MAX_TOKENS,
    README_CHARS,
    TYPICAL_OUTPUT,
    BatchRunner,
    Decision,
    DecisionClient,
    RepoInput,
    typical_input_tokens,
)
from startrend.clients.github import GitHubClient, GitHubError
from startrend.clients.llm import Usage, cost
from startrend.core import hashing, io, meta, week, weekfile

NEED = 15
EXPECTED_AI_RATIO = 0.4   # 묶음 크기를 정하는 가정 — 정답 세트·첫 실행으로 실측해 바꾼다
MODEL = "claude-opus-5-5"
MAX_ROUNDS = 20


def next_round(pool: Mapping[str, Sequence[int]], known: Mapping[int, bool | None], *, need: int = NEED,
               ratio: float = EXPECTED_AI_RATIO) -> list[int]:
    """다음에 판정할 저장소. known: True(AI) · False(비AI) · None(미분류·거절 — 다시 묻지 않는다)."""
    picks: list[int] = []
    for order in pool.values():
        ai = 0
        extra: list[int] = []
        for rid in order:
            if ai + len(extra) * ratio >= need:
                break
            if rid not in known:
                extra.append(rid)
            elif known[rid] is True:
                ai += 1
        picks.extend(x for x in extra if x not in picks)
    return picks


def input_hash(item: RepoInput, fingerprint: str) -> str:
    return hashing.content_hash({
        "fingerprint": fingerprint, "name": item.full_name, "description": item.description,
        "topics": list(item.topics), "language": item.language, "readme": item.readme_head[:README_CHARS],
    })[:16]


def load_pools(data_dir: Path, weeks: Sequence[date]) -> dict[str, list[int]]:
    pools: dict[str, list[int]] = {}
    for w in weeks:
        p = data_dir / "weekly" / week.week_name(w) / "rankings.json"
        if not p.exists():
            continue
        for axis, ids in (io.read_json(p).get("pool") or {}).items():
            pools[f"{week.week_name(w)}/{axis}"] = [int(i) for i in ids]
    return pools


def names_for(data_dir: Path, weeks: Sequence[date]) -> dict[int, str]:
    names: dict[int, str] = {}
    for w in weeks:
        p = weekfile.week_path(data_dir, w)
        if p.exists():
            names.update((rid, r.full_name) for rid, r in weekfile.read(p).items())
    return names


def _known_from(c: Mapping[str, Any]) -> bool | None:
    return bool(c.get("is_ai")) if c.get("status") == "ok" else None


def _numbered(batch: BatchRunner | None, n: int) -> BatchRunner | None:
    """Batch 차수 앞에 classify 묶음 번호를 붙인다 — 상태 파일 이름이 묶음마다 다르게."""
    if batch is None:
        return None

    def runner(reqs: dict[str, Any], tag: str) -> dict[str, Any]:
        return batch(reqs, f"{n}-{tag}")
    return runner


def run_classify(gh: GitHubClient, decider: DecisionClient, *, data_dir: Path, weeks: Sequence[date],
                 need: int = NEED, ratio: float = EXPECTED_AI_RATIO, today: date | None = None,
                 batch: BatchRunner | None = None, log: Callable[[str], None] = print) -> dict[str, Any]:
    """batch 가 있으면 묶음마다 판정 후보를 모아 Batch 로 보낸다(FR-3.7). 없으면 한 건씩."""
    pools = load_pools(data_dir, weeks)
    names = names_for(data_dir, weeks)
    known: dict[int, bool | None] = {}
    stats: dict[str, Any] = {"rounds": 0, "decided": 0, "reused": 0, "github_calls": 0, "stopped": None,
                             "unclassified": [], "missing": []}
    stamp = (today or date.today()).isoformat()
    hashes: dict[int, str] = {}

    def save(item: RepoInput, d: Decision) -> None:
        # 판정이 끝나는 대로 저장한다 — 다음 Batch 가 예산에 걸려도 이미 받은 결과는 남는다
        record = {"status": d.status, "is_ai": d.is_ai, "type": d.type, "category": d.category,
                  "secondary": d.secondary, "reason": d.reason, "attempts": d.attempts, "error": d.error,
                  "confidence": d.confidence, "input_hash": hashes[item.repo_id],
                  "fingerprint": decider.fingerprint, "at": stamp}
        meta.save(data_dir, {"id": item.repo_id, "full_name": item.full_name, "classify": record})
        known[item.repo_id] = _known_from(record)
        stats["decided"] += 1
        if d.status != "ok":
            stats["unclassified"].append(item.full_name)

    for _ in range(MAX_ROUNDS):
        ids = next_round(pools, known, need=need, ratio=ratio)
        if not ids:
            break
        stats["rounds"] += 1
        n = stats["rounds"]
        pending: list[RepoInput] = []
        for rid in ids:
            name = names.get(rid)
            try:
                if name is None:
                    raise GitHubError(f"주간 파일에 없는 저장소 {rid}")
                repo = gh.get_repo(name)
                readme = gh.readme(name) or ""
                stats["github_calls"] += 2
            except GitHubError:
                known[rid] = None
                stats["missing"].append(name or str(rid))
                continue
            item = RepoInput(rid, repo.full_name, repo.description, tuple(repo.topics), repo.language,
                             readme[:README_CHARS])
            h = input_hash(item, decider.fingerprint)
            old = (meta.load(data_dir, rid) or {}).get("classify") or {}
            if old.get("input_hash") == h:
                known[rid] = _known_from(old)
                stats["reused"] += 1
                continue
            pending.append(item)
            hashes[rid] = h
        log(f"  묶음 {n}: 판정 후보 {len(ids)}개 — 새로 판정 {len(pending)}개")
        try:
            decider.classify_many(pending, batch=_numbered(batch, n), on_decision=save)
        except BudgetExceeded as e:
            stats["stopped"] = "budget"
            log(f"  예산 상한 — 여기서 멈춘다: {e}")
            return stats
    return stats


def dry_run(*, data_dir: Path, weeks: Sequence[date], system_prompt: str, need: int = NEED,
            ratio: float = EXPECTED_AI_RATIO, batch: bool = True) -> dict[str, Any]:
    """호출 0회. 저장된 판정은 입력이 그대로라고 보고, 첫 묶음과 최대 판정 수·비용 범위를 낸다."""
    pools = load_pools(data_dir, weeks)
    known: dict[int, bool | None] = {}
    for rid in {i for ids in pools.values() for i in ids}:
        c = (meta.load(data_dir, rid) or {}).get("classify")
        if c:
            known[rid] = _known_from(c)
    first = next_round(pools, known, need=need, ratio=ratio)
    upper = len({i for ids in pools.values() for i in ids if i not in known})
    tokens_in = typical_input_tokens(system_prompt)
    lo = cost(MODEL, Usage(tokens_in, TYPICAL_OUTPUT), batch=batch)
    hi = cost(MODEL, Usage(tokens_in, MAX_TOKENS), batch=batch)
    return {
        "first_round": len(first), "upper_bound": upper, "already_known": len(known),
        "per_item_usd": (lo, hi), "first_round_usd": (len(first) * lo, len(first) * hi),
        "upper_usd": (upper * lo, upper * hi), "github_calls_first_round": 2 * len(first),
        "assumptions": {"ai_ratio": ratio, "input_tokens_per_item": tokens_in,
                        "output_tokens": (TYPICAL_OUTPUT, MAX_TOKENS), "batch": batch},
    }
