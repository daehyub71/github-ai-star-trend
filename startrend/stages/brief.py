"""주간 브리핑 1장 (SPEC FR-8.2·8.3·8.4) — 과금 단계(주 1회 호출). dry-run 이 먼저다(NFR-2).

- 코드가 채운다: 뜨는·식는 카테고리 표(이번 주 비중 대 앞 4주 평균, FR-8.1 의 집계) · 새로 들어온 저장소
  (그 전 어느 AI 탭에도 없던 것) · 이번 주 범위(커버리지·카드 수).
- LLM 은 헤드라인 · "왜 지금" 2~3개 · 시사점 3~5개만 쓴다. 저장소는 번호(R1…)로만 가리키고, 링크는 코드가
  만든다 — 주장마다 저장소(카드)에 연결된다(FR-8.3). 인용 게이트를 지난다. 새 웹 검색은 하지 않는다.
- 입력은 그 주 랭킹 · 카테고리 추이 · 최신 카드 보관소(core.cards). 결과는 결정 53 에 따라 공개 저장소 밖
  `.work/<주>/briefing.md`(자리는 Phase 5).
"""

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

from startrend import gate
from startrend.budget import BudgetExceeded
from startrend.clients.llm import LLMClient, LLMRequest, Usage, cost, request_tokens
from startrend.core import cards, io, untrusted, week
from startrend.core.cards import CardStore

PROMPT_FILE = Path(__file__).resolve().parents[1] / "prompts" / "brief.md"
MODEL = "claude-opus-5-5"
EFFORT = "medium"
MAX_TOKENS = 8_000
TYPICAL_OUTPUT = 2_000       # dry-run 하한 가정 — 첫 실행으로 실측
MOVE_WEEKS = 4               # 비중 변화를 견주는 앞 주 수
TOP_MOVES = 3
CITED = ("왜 지금", "시사점")  # 주장마다 저장소 링크가 있어야 하는 섹션 (FR-8.3)
AXIS_ORDER = ("gain", "fresh", "growth", "total")
BASES = ("확인", "추정")


class BriefError(Exception):
    """브리핑을 만들지 못했다 — 거절·형식 오류(두 번)·출력 한도."""


@dataclass(frozen=True)
class Move:
    category: str
    name: str
    share_now: float
    share_before: float

    @property
    def delta(self) -> float:
        return self.share_now - self.share_before


@dataclass
class BriefRepo:
    ref: str                              # R1 …
    repo_id: int
    full_name: str
    category: str                         # 이름
    description: str
    is_new: bool                          # 그 전 어느 AI 탭에도 없었다
    summary: dict[str, str] | None        # 카드 ① (보관소에 카드가 있을 때)


@dataclass
class BriefInput:
    week_start: date
    until: date
    repos: list[BriefRepo]
    rising: list[Move]
    cooling: list[Move]
    coverage: float | None


def _share(cats: Mapping[str, Any], cid: str) -> float:
    total = (cats.get("ALL") or {}).get("gain") or 0
    return ((cats.get("categories") or {}).get(cid, {}).get("gain", 0) / total) if total else 0.0


def category_moves(cur: Mapping[str, Any], prev: Sequence[Mapping[str, Any]],
                   names: Mapping[str, str]) -> tuple[list[Move], list[Move]]:
    """이번 주 비중 대 앞 주 평균 비중 — 가장 많이 오른 것·내린 것 TOP_MOVES 개씩."""
    ids = set(cur.get("categories") or {}) | {c for p in prev for c in (p.get("categories") or {})}
    moves = [Move(c, names.get(c, c), _share(cur, c), mean(_share(p, c) for p in prev) if prev else 0.0)
             for c in sorted(ids)]
    rising = sorted((m for m in moves if m.delta > 1e-9), key=lambda m: (-m.delta, m.category))[:TOP_MOVES]
    cooling = sorted((m for m in moves if m.delta < -1e-9), key=lambda m: (m.delta, m.category))[:TOP_MOVES]
    return rising, cooling


def _ai_entries(ranking: Mapping[str, Any]) -> list[dict[str, Any]]:
    seen: dict[int, dict[str, Any]] = {}
    for a in AXIS_ORDER:
        for e in ((ranking.get("axes") or {}).get(a) or {}).get("ai") or []:
            seen.setdefault(e["id"], e)
    return list(seen.values())


def seen_before(data_dir: Path, week_start: date) -> set[int]:
    """그 주 전의 어느 AI 탭에든 있었던 저장소."""
    out: set[int] = set()
    for p in sorted((data_dir / "weekly").glob("*/rankings.json")):
        if p.parent.name < week.week_name(week_start):
            out.update(e["id"] for e in _ai_entries(io.read_json(p)))
    return out


def load_input(data_dir: Path, store: CardStore, week_start: date, *, names: Mapping[str, str]) -> BriefInput:
    wdir = data_dir / "weekly" / week.week_name(week_start)
    if not (wdir / "rankings.json").exists():
        raise FileNotFoundError(f"랭킹이 없다: {wdir / 'rankings.json'}")
    before = seen_before(data_dir, week_start)
    repos = []
    for i, e in enumerate(_ai_entries(io.read_json(wdir / "rankings.json")), 1):
        stored = store.load(e["id"])
        cat = e.get("category")
        repos.append(BriefRepo(f"R{i}", e["id"], e["full_name"], names.get(cat, cat) if cat else "—",
                               " ".join(str(e.get("description") or "").split()), e["id"] not in before,
                               cards.summary(stored.markdown) if stored else None))
    cur = io.read_json(wdir / "categories.json") if (wdir / "categories.json").exists() else {}
    prev = []
    for k in range(1, MOVE_WEEKS + 1):
        p = data_dir / "weekly" / week.week_name(week_start - timedelta(days=7 * k)) / "categories.json"
        if p.exists():
            prev.append(io.read_json(p))
    rising, cooling = category_moves(cur, prev, names) if cur else ([], [])
    return BriefInput(week_start, week.week_end(week_start), repos, rising, cooling, cur.get("coverage"))


# --- 요청 ---


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _moves(ms: Sequence[Move]) -> str:
    return ", ".join(f"{m.name} {_pct(m.share_before)} → {_pct(m.share_now)}" for m in ms) or "none"


def user_message(bi: BriefInput) -> str:
    facts = [f"week: {bi.week_start.isoformat()} ~ {bi.until.isoformat()}",
             f"rising categories (share this week vs previous 4-week average): {_moves(bi.rising)}",
             f"cooling categories: {_moves(bi.cooling)}",
             f"new to the AI tab this week: {sum(r.is_new for r in bi.repos)} of {len(bi.repos)}",
             "scope: only classified repositories near the top of the rankings are counted"]
    items = []
    for r in bi.repos:
        lines = [f"[{r.ref}] {r.full_name} · {r.category}" + (" · 처음 들어옴" if r.is_new else "")]
        if r.summary:
            lines += [f"card what: {r.summary['what']}", f"card why now: {r.summary['why_now']}",
                      f"card meaning: {r.summary['meaning']}"]
        else:
            lines.append("card: none")
        lines.append(f"description: {r.description or '(none)'}")
        items.append("\n".join(lines))
    doc = untrusted.block("document", "\n".join(facts))
    return f"{doc}\n{untrusted.block('evidence', chr(10).join(items))}"


_CLAIM = {"repos": {"type": "array", "items": {"type": "string"}}, "text": {"type": "string"},
          "basis": {"type": "string", "enum": list(BASES)}}


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


SCHEMA: dict[str, Any] = _obj({"headline": {"type": "string"},
                               "why_now": {"type": "array", "items": _obj(_CLAIM)},
                               "implications": {"type": "array", "items": _obj(_CLAIM)}})


@dataclass(frozen=True)
class BriefClaim:
    repos: tuple[str, ...]
    text: str
    basis: str


@dataclass(frozen=True)
class BriefDraft:
    headline: str
    why_now: tuple[BriefClaim, ...]
    implications: tuple[BriefClaim, ...]


def _claims(raw: Any, name: str) -> tuple[BriefClaim, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"{name} must be a list")
    out = []
    for c in raw:
        if not isinstance(c, dict) or not isinstance(c.get("text"), str) or not c["text"].strip():
            raise ValueError(f"{name}: every item needs non-empty text")
        if c.get("basis") not in BASES:
            raise ValueError(f"{name}: basis must be one of {list(BASES)}, got {c.get('basis')!r}")
        refs = c.get("repos") or []
        if not isinstance(refs, list) or not all(isinstance(r, str) for r in refs):
            raise ValueError(f"{name}: repos must be a list of ids like R3")
        out.append(BriefClaim(tuple(r.strip() for r in refs), " ".join(c["text"].split()), c["basis"]))
    return tuple(out)


def parse_brief(text: str) -> BriefDraft:
    try:
        d = json.loads(text)
    except ValueError as e:
        raise ValueError(f"not JSON ({e})") from e
    if not isinstance(d, dict) or not isinstance(d.get("headline"), str) or not d["headline"].strip():
        raise ValueError("headline must be non-empty text")
    return BriefDraft(" ".join(d["headline"].split()), _claims(d.get("why_now"), "why_now"),
                      _claims(d.get("implications"), "implications"))


class BriefWriter:
    def __init__(self, llm: LLMClient, *, effort: str = EFFORT, max_tokens: int = MAX_TOKENS):
        self.llm = llm
        self.effort = effort
        self.max_tokens = max_tokens
        self.system = PROMPT_FILE.read_text(encoding="utf-8")
        self.prompt_hash = hashlib.sha256(self.system.encode("utf-8")).hexdigest()[:16]

    @property
    def fingerprint(self) -> str:
        return f"{self.prompt_hash}:{self.llm.model}:{self.effort}"

    def request(self, bi: BriefInput, *, error: str = "") -> LLMRequest:
        user = user_message(bi)
        if error:
            user += (f"\n\nYour previous answer was rejected: {error}. "
                     "Answer again in the required JSON shape.")
        return LLMRequest(system=self.system, user=user, max_tokens=self.max_tokens, effort=self.effort,
                          schema=SCHEMA, purpose="brief")

    def draft(self, bi: BriefInput) -> BriefDraft:
        error = ""
        for _ in (1, 2):
            resp = self.llm.complete(self.request(bi, error=error))
            if resp.stop_reason == "refusal":
                raise BriefError("refusal")
            if resp.stop_reason == "max_tokens":
                raise BriefError("max_tokens — 출력 한도에 걸려 JSON 이 잘렸다")
            try:
                return parse_brief(resp.text)
            except ValueError as e:
                error = str(e)
        raise BriefError(f"형식 오류 두 번: {error}")


# --- 렌더 ---


def _link(r: BriefRepo) -> str:
    return f"[{r.full_name}](https://github.com/{r.full_name})"


def _clean(s: str) -> str:
    return re.sub(r"[\[\]\n]", " ", s).strip()


def render_brief(bi: BriefInput, dr: BriefDraft, *, generated: date,
                 fingerprint: str) -> tuple[str, gate.GateResult]:
    by_ref = {r.ref: r for r in bi.repos}
    lines = [f"# 이번 주 AI 트렌드 — {bi.week_start.isoformat()} ~ {bi.until.isoformat()}", "",
             dr.headline, "", "## 뜨는 카테고리 · 식는 카테고리"]
    if bi.rising or bi.cooling:
        lines += ["| 카테고리 | 이번 주 비중 | 앞 4주 평균 | 변화 |", "|---|---:|---:|---:|"]
        lines += [f"| {m.name} | {_pct(m.share_now)} | {_pct(m.share_before)} | "
                  f"{'▲' if m.delta > 0 else '▼'} {abs(m.delta) * 100:.1f}%p |"
                  for m in (*bi.rising, *bi.cooling)]
    else:
        lines.append("카테고리 추이가 아직 없다.")
    cov = f"커버리지 {bi.coverage * 100:.0f}%" if isinstance(bi.coverage, (int, float)) else "커버리지 모름"
    lines += ["", f"범위: 판정된 저장소(랭킹 후보 쪽)의 증가만 집계했다 — 이번 주 {cov}.", "",
              "## 새로 들어온 저장소"]
    new = [r for r in bi.repos if r.is_new]
    lines += [f"- {_link(r)} — {_clean((r.summary or {}).get('what') or r.description or '설명 없음')}"
              f" · {r.category}" for r in new] or ["이번 주 처음 AI 탭에 든 저장소는 없다."]
    lines += ["", "## 왜 지금 — 주목할 저장소"]
    for c in dr.why_now:
        repo = next((by_ref[x] for x in c.repos if x in by_ref), None)
        lines.append(f"- {_link(repo)} — {c.text} ({c.basis})" if repo else f"- {c.text} ({c.basis})")
    lines += ["", "## 시사점"]
    for c in dr.implications:
        links = " · ".join(_link(by_ref[x]) for x in c.repos if x in by_ref)
        lines.append(f"- {c.text}" + (f" {links}" if links else "") + f" ({c.basis})")
    with_card = sum(1 for r in bi.repos if r.summary)
    lines += ["", "## 이번 주 범위",
              f"AI 탭 {len(bi.repos)}개 중 카드가 있는 저장소 {with_card}개 · "
              f"처음 들어온 저장소 {len(new)}개. "
              "숫자는 코드가 계산했고, 글은 카드 요약과 저장소 설명만 근거로 썼다(새 검색 없음).", ""]
    body = "\n".join(lines)
    res = gate.check(body, [], repos=[r.full_name for r in bi.repos], cited=CITED)
    front = ["---", f"week: {bi.week_start.isoformat()}", f"as_of: {bi.until.isoformat()}",
             f"generated: {generated.isoformat()}", f"fingerprint: {fingerprint}", f"repos: {len(bi.repos)}",
             f"cards: {with_card}", f"gate_checked: {res.checked}", f"gate_excluded: {len(res.excluded)}",
             "---", ""]
    return "\n".join(front) + res.body, res


# --- 실행 ---


def run_brief(writer: BriefWriter, bi: BriefInput, *, work_dir: Path, today: date,
              log: Callable[[str], None] = print) -> dict[str, Any]:
    out = work_dir / week.week_name(bi.week_start)
    stats: dict[str, Any] = {"written": False, "stopped": None, "error": None, "excluded_claims": 0}
    try:
        dr = writer.draft(bi)
    except BudgetExceeded as e:
        stats["stopped"] = "budget"
        log(f"  예산 상한 — 브리핑을 쓰지 않는다: {e}")
        return stats
    except BriefError as e:
        stats["error"] = str(e)
        log(f"  브리핑 실패 — {e}")
        return stats
    md, res = render_brief(bi, dr, generated=today, fingerprint=writer.fingerprint)
    io.write_text_atomic(out / "briefing.md", md)
    io.write_json(out / "briefing.gate.json", {"checked": res.checked, "kept_links": res.kept_links,
                                               "excluded": res.log()})
    io.write_json(out / "briefing.draft.json", asdict(dr))
    stats.update(written=True, excluded_claims=len(res.excluded), file=str(out / "briefing.md"))
    log(f"  브리핑 작성 — 게이트 제외 {len(res.excluded)}건")
    return stats


def dry_run(writer: BriefWriter, bi: BriefInput) -> dict[str, Any]:
    """호출 0 — 실제로 보낼 요청 하나로 입력 토큰과 비용 범위를 낸다(FR-8.4)."""
    req = writer.request(bi)
    typ = request_tokens(req.system, req.user, schema=True, typical=True)
    cons = request_tokens(req.system, req.user, schema=True)
    lo = cost(MODEL, Usage(typ, TYPICAL_OUTPUT))
    hi = cost(MODEL, Usage(cons, writer.max_tokens))
    return {"llm_calls": 1, "repos": len(bi.repos), "cards": sum(1 for r in bi.repos if r.summary),
            "new_repos": sum(r.is_new for r in bi.repos), "input_tokens": [typ, cons],
            "total_usd": [round(lo, 4), round(hi, 4)],
            "assumptions": {"model": MODEL, "effort": writer.effort, "output_tokens": [TYPICAL_OUTPUT,
                                                                                       writer.max_tokens]},
            "fingerprint": writer.fingerprint}
