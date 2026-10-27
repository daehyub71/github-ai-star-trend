"""분류 정답 세트 후보 뽑기 (SPEC FR-14.1, 결정 41). 비용 0, 결정론(seed).

아직 분류 전이라 AI 여부를 모른다. 그래서 설명·토픽·이름의 AI 단어로 "신호"(강·약·없음)를 매겨
층을 나눈다 — **정답이 아니라 고루 뽑기 위한 대리 지표**다.

- 랭킹 진입 저장소 60개: 실제 분류 대상이 랭킹 후보다(결정 30). 그 분포를 담는다.
- 나머지 140개: 신호 강 60 · 약 40 · 없음 40. 그룹 안에서는 (규모, 새 저장소) 칸을 돌아가며 하나씩 뽑아
  규모가 고르게 섞이게 한다.
- 블라인드 30개: 랭킹 10 + 나머지 20(신호별로 고르게). Claude 초안 없이 사용자가 직접 라벨해 초안 편향을 잰다.
- 모자란 그룹은 나머지 그룹에서 채워 전체 수를 맞춘다. 보관(archived) 저장소는 뺀다.
"""

import random
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from startrend.budget import BudgetExceeded
from startrend.clients.decision import README_CHARS, BatchRunner, Decision, DecisionClient, RepoInput
from startrend.clients.github import GitHubClient, GitHubError
from startrend.core import io
from startrend.core.models import Repo

GROUPS = ("ranked", "strong", "weak", "none")
QUOTA = {"ranked": 60, "strong": 60, "weak": 40, "none": 40}
BLIND_RANKED = 10

# 이 단어(토픽 또는 설명·이름의 단어)가 있으면 AI 저장소일 가능성이 높다
STRONG_WORDS = {
    "llm", "llms", "gpt", "chatgpt", "openai", "anthropic", "claude", "gemini", "llama", "ollama", "mcp",
    "rag", "agent", "agents", "agentic", "langchain", "transformer", "transformers", "diffusion", "pytorch",
    "tensorflow", "huggingface", "lora", "finetune", "finetuning", "vllm", "embedding", "embeddings",
    "deepseek", "qwen", "mistral", "copilot", "chatbot", "genai", "multimodal", "whisper", "tts", "nlp",
}
STRONG_PHRASES = ("model context protocol", "machine learning", "deep learning", "neural network",
                  "language model", "generative ai", "fine-tun", "hugging face", "computer vision",
                  "speech recognition", "artificial intelligence")
STRONG_TOPICS = STRONG_WORDS | {"ai", "ml", "ai-agent", "ai-agents", "machine-learning", "deep-learning",
                                "large-language-models", "generative-ai", "artificial-intelligence",
                                "model-context-protocol", "stable-diffusion", "prompt-engineering",
                                "computer-vision", "vector-database"}
# 이것만 있으면 애매하다 — AI 일 수도 아닐 수도
WEAK_WORDS = {"ai", "ml", "model", "models", "bot", "bots", "assistant", "smart", "intelligent", "neural",
              "prompt", "prompts", "automation", "autonomous", "vision", "voice"}
_WORD = re.compile(r"[a-z0-9]+")


def signal(r: Repo) -> str:
    topics = {t.lower() for t in r.topics}
    text = f"{r.full_name.split('/', 1)[-1]} {r.description or ''}".lower()
    words = set(_WORD.findall(text))
    if topics & STRONG_TOPICS or words & STRONG_WORDS or any(p in text for p in STRONG_PHRASES):
        return "strong"
    if words & WEAK_WORDS:
        return "weak"
    return "none"


def band(stars: int) -> str:
    if stars < 1000:
        return "<1k"
    if stars < 5000:
        return "1k-5k"
    if stars < 50_000:
        return "5k-50k"
    return "50k+"


def _round_robin(members: list[Repo], key: Any, take: int, rng: random.Random) -> list[Repo]:
    """칸(key)마다 섞은 뒤 칸을 돌아가며 하나씩 — 칸이 고르게 섞인다."""
    cells: dict[Any, list[Repo]] = {}
    for r in sorted(members, key=lambda x: x.id):
        cells.setdefault(key(r), []).append(r)
    for k in sorted(cells):
        rng.shuffle(cells[k])
    out: list[Repo] = []
    while len(out) < take and any(cells.values()):
        for k in sorted(cells):
            if cells[k] and len(out) < take:
                out.append(cells[k].pop())
    return out


def _split(total: int, parts: int) -> list[int]:
    base, rest = divmod(total, parts)
    return [base + (1 if i < rest else 0) for i in range(parts)]


def sample(repos: Mapping[int, Repo], *, ranked: set[int], new: set[int], n: int = 200, blind: int = 30,
           seed: int = 20261027) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    pool = {rid: r for rid, r in repos.items() if not r.archived}
    sig = {rid: signal(r) for rid, r in pool.items()}

    def cell(r: Repo) -> tuple[str, bool]:
        return band(r.stars), r.id in new

    members = {g: [r for rid, r in pool.items() if rid not in ranked and sig[rid] == g] for g in GROUPS[1:]}
    members["ranked"] = [r for rid, r in pool.items() if rid in ranked]
    scale = n / sum(QUOTA.values())
    want = {g: round(QUOTA[g] * scale) for g in GROUPS}

    picked: dict[str, list[Repo]] = {}
    for g in GROUPS:
        key = (lambda r: (sig[r.id], *cell(r))) if g == "ranked" else cell
        picked[g] = _round_robin(members[g], key, want[g], rng)
    # 모자란 그룹은 신호 그룹에서 비율대로 채운다
    short = n - sum(len(v) for v in picked.values())
    while short > 0:
        before = short
        for g in GROUPS[1:]:
            if short == 0:
                break
            taken = {r.id for r in picked[g]}
            extra = _round_robin([r for r in members[g] if r.id not in taken], cell, 1, rng)
            picked[g] += extra
            short -= len(extra)
        if short == before:
            break  # 모집단이 n 보다 작다

    blind_ids: set[int] = set()
    b_ranked = min(BLIND_RANKED, len(picked["ranked"]))
    quotas = [b_ranked, *_split(blind - b_ranked, 3)]
    for g, q in zip(GROUPS, quotas, strict=True):
        ids = sorted(r.id for r in picked[g])
        blind_ids |= set(rng.sample(ids, min(q, len(ids))))

    out = []
    for g in GROUPS:
        for r in picked[g]:
            out.append({
                "repo_id": r.id, "full_name": r.full_name, "description": r.description,
                "topics": list(r.topics), "language": r.language, "stars": r.stars,
                "created": r.created_at.date().isoformat(), "group": g, "signal": sig[r.id],
                "band": band(r.stars), "new": r.id in new, "blind": r.id in blind_ids,
            })
    return sorted(out, key=lambda p: p["repo_id"])


# --- 초안 (P2-11, 결정 41) — 과금 단계. CLI 가 dry-run 을 먼저 보인다 ---


def draft_inputs(gh: GitHubClient, candidates: Sequence[Mapping[str, Any]],
                 log: Callable[[str], None] = print) -> tuple[list[RepoInput], list[str]]:
    """판정 입력 — classify 와 같은 모양(저장소 정보 + README 앞부분). 받을 수 없는 저장소는 이름만 남긴다."""
    items: list[RepoInput] = []
    missing: list[str] = []
    for c in candidates:
        name = str(c["full_name"])
        try:
            repo = gh.get_repo(name)
            readme = gh.readme(name) or ""
        except GitHubError:
            missing.append(name)
            continue
        items.append(RepoInput(repo.id, repo.full_name, repo.description, tuple(repo.topics), repo.language,
                               readme[:README_CHARS]))
    log(f"  판정 입력 {len(items)}개 · 받지 못함 {len(missing)}개")
    return items, missing


def run_draft(gh: GitHubClient, decider: DecisionClient, candidates: Sequence[Mapping[str, Any]], *,
              out: Path, batch: BatchRunner | None = None, today: date | None = None,
              log: Callable[[str], None] = print) -> dict[str, Any]:
    """후보 전부(블라인드 포함)를 판정해 초안 파일(판정 결과 형식)로 남긴다.

    블라인드 30개의 초안은 사용자 라벨과 맞대어 초안 편향을 잰다(FR-14.1). 예산 상한에 걸려도
    그때까지 판정한 것은 파일에 남는다.
    """
    items, missing = draft_inputs(gh, candidates, log)
    stamp = (today or date.today()).isoformat()
    blind = {int(c["repo_id"]): bool(c.get("blind")) for c in candidates}
    rows: dict[int, dict[str, Any]] = {}

    def save(item: RepoInput, d: Decision) -> None:
        rows[item.repo_id] = {
            "repo_id": item.repo_id, "full_name": item.full_name, "blind": blind.get(item.repo_id, False),
            "status": d.status, "is_ai": d.is_ai, "type": d.type, "category": d.category,
            "secondary": d.secondary, "reason": d.reason, "attempts": d.attempts, "error": d.error,
            "confidence": d.confidence, "fingerprint": decider.fingerprint, "at": stamp}

    stats: dict[str, Any] = {"candidates": len(candidates), "inputs": len(items), "missing": missing,
                             "decided": 0, "stopped": None}
    try:
        decider.classify_many(items, batch=batch, on_decision=save)
    except BudgetExceeded as e:
        stats["stopped"] = "budget"
        log(f"  예산 상한 — 여기서 멈춘다: {e}")
    finally:
        order = [int(c["repo_id"]) for c in candidates]
        io.write_jsonl(out, [rows[i] for i in order if i in rows])
    stats["decided"] = len(rows)
    stats["not_ok"] = sum(1 for r in rows.values() if r["status"] != "ok")
    return stats
