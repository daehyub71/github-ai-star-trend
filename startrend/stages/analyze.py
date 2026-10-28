"""심층 카드 (SPEC FR-6.1·6.2·6.4·6.5·6.6, FR-7, NFR-7) — 과금 단계. dry-run 이 먼저다(NFR-2).

- 입력은 근거 목록(`.work/<주>/evidence.jsonl` + 원문)과 그 주 랭킹·일별 곡선이다(PLAN 1-4).
- LLM 은 정해진 JSON 으로 글만 쓴다. **출처는 근거 번호(E1…)로만 단다** — 링크는 코드가 근거 목록에서 만들므로
  지어낸 URL 이 처음부터 들어올 수 없다. 인용 게이트(FR-7)는 그 위의 두 번째 방어다.
- 숫자(② 숫자 표·⑦ 사실 표)는 코드가 채운다(FR-6.5). 비교 저장소는 GitHub 에 실제로 있는 것만 링크를 허용한다.
- 기준일(as_of)은 그 주의 끝이다(FR-6.4). 지시문 해시·모델·effort 를 카드에 남긴다(PLAN 1-5).
- 시범 카드는 D-23(공개 저장소에 둘지) 전까지 `.work/<주>/cards/` 에만 쓴다. 재등장 카드의 변경 기록은 P3-10.
"""

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from startrend import gate
from startrend.budget import BudgetExceeded
from startrend.clients.llm import LLMClient, LLMRequest, Usage, cost, request_tokens
from startrend.core import evidence as ev
from startrend.core import io, spikes, untrusted, week, weekfile
from startrend.core.evidence import Target
from startrend.core.spikes import Spike

PROMPT_FILE = Path(__file__).resolve().parents[1] / "prompts" / "card.md"
MODEL = "claude-opus-5-5"
EFFORT = "medium"
MAX_TOKENS = 16_000          # 사고 + JSON. 일반 호출 한도 안(스트리밍 없이 10분 미만)
TYPICAL_OUTPUT = 3_600       # dry-run 하한 — 카드 시범 5장 실측 3,328~3,774(중앙값 3,557, MEASURE §23)
README_CHARS = 6_000
RELEASE_CHARS = 1_500
DOC_CHARS = 800
SPIKE_WEEKS = 5
AXIS_ORDER = ("gain", "fresh", "growth", "total")
AXIS_LABEL = {"gain": "지금 뜨는", "fresh": "새로 뜨는", "growth": "규모 대비 급성장", "total": "누적 TOP"}
BASES = ("확인", "추정")
NO_ITEMS = "근거가 있는 항목이 없다."
_REPO_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")

_CLAIM = {"text": {"type": "string"}, "sources": {"type": "array", "items": {"type": "string"}},
          "basis": {"type": "string", "enum": list(BASES)}}


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


SCHEMA: dict[str, Any] = _obj({
    "summary": _obj({k: {"type": "string"} for k in ("what", "why_now", "meaning")}),
    "why_now": {"type": "array", "items": _obj({"date": {"type": "string"}, **_CLAIM})},
    "what_it_is": {"type": "string"},
    "comparison": {"type": "array", "items": _obj({"repo": {"type": "string"}, **_CLAIM})},
    "use_cases": {"type": "array", "items": _obj(_CLAIM)},
    "risks": {"type": "array", "items": _obj(_CLAIM)},
})


class CardError(Exception):
    """카드를 만들지 못했다 — 거절·형식 오류(두 번)·출력 한도."""


# --- 입력 ---


@dataclass
class CardInput:
    target: Target
    entry: dict[str, Any]                     # 그 주 랭킹 항목 (숫자는 여기서 온다)
    ranks: list[tuple[str, int]]              # AI 탭 (축, 순위)
    docs: list[ev.Evidence]                   # 원문이 붙은 근거 — 번호는 1부터 이 순서
    failed_sources: list[str] = field(default_factory=list)
    spikes: list[Spike] = field(default_factory=list)


def load_inputs(data_dir: Path, work_dir: Path, week_start: date, *,
                repos: Sequence[str] | None = None) -> list[CardInput]:
    """근거를 모은 저장소 중 그 주 AI 탭에 있는 것. 근거 목록 순서대로."""
    ranking = io.read_json(data_dir / "weekly" / week.week_name(week_start) / "rankings.json")
    entries: dict[int, dict[str, Any]] = {}
    ranks: dict[int, list[tuple[str, int]]] = {}
    for a in AXIS_ORDER:
        for i, e in enumerate((ranking.get("axes", {}).get(a) or {}).get("ai") or [], 1):
            entries.setdefault(e["id"], e)
            ranks.setdefault(e["id"], []).append((a, int(e.get("rank") or i)))
    want = {r.lower() for r in repos} if repos else None
    rows = {w: weekfile.read(p) for k in range(SPIKE_WEEKS)
            if (p := weekfile.week_path(data_dir, w := week_start - timedelta(days=7 * k))).exists()}
    out = []
    for rid, c in ev.read(work_dir, week_start, with_text=True).items():
        if rid not in entries or (want is not None and c.target.full_name.lower() not in want):
            continue
        e = entries[rid]
        daily = spikes.daily_from_weeks({w: r[rid] for w, r in rows.items() if rid in r})
        created = date.fromisoformat(e["created"]) if e.get("created") else None
        docs = [d for d in c.docs if not _after(d, c.target.until)]
        out.append(CardInput(c.target, e, ranks[rid], docs, c.failed_sources,
                             spikes.find_spikes(daily, created=created)))
    return out


def _after(d: ev.Evidence, as_of: date) -> bool:
    """기준일 뒤에 나온 근거인가 — 카드는 기준일 시점의 문서다(FR-6.4, 2026-10-28 시범 검토 뒤 사용자 결정).
    날짜가 없거나 읽을 수 없으면 뒤로 보지 않는다(README 등)."""
    try:
        return date.fromisoformat((d.published_at or "")[:10]) > as_of
    except ValueError:
        return False


# --- 요청 ---


def _doc_block(i: int, d: ev.Evidence) -> str:
    day = (d.published_at or "")[:10]
    head = f"[E{i}] {d.source} · {d.kind}" + (f" · {day}" if day else "") + f" · {d.url}"
    limit = README_CHARS if d.kind == "repo" else RELEASE_CHARS if d.kind == "release" else DOC_CHARS
    body = (d.text or d.excerpt)[:limit].strip()
    title = f"title: {d.title}\n" if d.title and d.kind != "repo" else ""
    label = "README:\n" if d.kind == "repo" else ""
    note = "\n(본문을 읽지 않는 출처 — 검색 스니펫만)" if d.extra.get("fetchable") is False else ""
    return f"{head}\n{title}{label}{body}{note}"


def _fmt_spike(s: Spike) -> str:
    return f"{s.day.isoformat()} +{s.stars:,}"


def user_message(ci: CardInput, names: Mapping[str, str] | None = None) -> str:
    e, t = ci.entry, ci.target
    names = names or {}
    cat = e.get("category")
    facts = [
        f"name: {t.full_name}",
        f"description: {e.get('description') or '(none)'}",
        f"type: {e.get('type') or '-'} · category: {names.get(cat, cat) if cat else '-'}",
        f"week: {t.since.isoformat()} ~ {t.until.isoformat()}",
        "rankings (AI tab): " + (" · ".join(f"{AXIS_LABEL[a]} {r}위" for a, r in ci.ranks) or "-"),
        "spike days: " + (", ".join(_fmt_spike(s) for s in ci.spikes) or "none found"),
    ]
    if ci.failed_sources:
        facts.append("sources that failed this week: " + ", ".join(ci.failed_sources))
    evidence = "\n\n".join(_doc_block(i, d) for i, d in enumerate(ci.docs, 1))
    return f"{untrusted.block('repository', chr(10).join(facts))}\n{untrusted.block('evidence', evidence)}"


@dataclass(frozen=True)
class Claim:
    text: str
    sources: tuple[str, ...]
    basis: str
    date: str = ""
    repo: str = ""


@dataclass(frozen=True)
class Summary:
    what: str
    why_now: str
    meaning: str


@dataclass(frozen=True)
class Draft:
    summary: Summary
    why_now: tuple[Claim, ...]
    what_it_is: str
    comparison: tuple[Claim, ...]
    use_cases: tuple[Claim, ...]
    risks: tuple[Claim, ...]


def _claims(raw: Any, field_name: str) -> tuple[Claim, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"{field_name} must be a list")
    out = []
    for c in raw:
        if not isinstance(c, dict) or not isinstance(c.get("text"), str) or not c["text"].strip():
            raise ValueError(f"{field_name}: every item needs non-empty text")
        if c.get("basis") not in BASES:
            raise ValueError(f"{field_name}: basis must be one of {list(BASES)}, got {c.get('basis')!r}")
        srcs = c.get("sources") or []
        if not isinstance(srcs, list) or not all(isinstance(s, str) for s in srcs):
            raise ValueError(f"{field_name}: sources must be a list of evidence ids like E3")
        day = str(c.get("date") or "")
        if day and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            day = ""
        out.append(Claim(" ".join(c["text"].split()), tuple(s.strip() for s in srcs), c["basis"], day,
                         str(c.get("repo") or "").strip()))
    return tuple(out)


def parse_draft(text: str) -> Draft:
    try:
        d = json.loads(text)
    except ValueError as e:
        raise ValueError(f"not JSON ({e})") from e
    if not isinstance(d, dict):
        raise ValueError("not a JSON object")
    s = d.get("summary")
    if not isinstance(s, dict) or not all(isinstance(s.get(k), str) and s[k].strip()
                                          for k in ("what", "why_now", "meaning")):
        raise ValueError("summary needs non-empty what, why_now and meaning")
    if not isinstance(d.get("what_it_is"), str) or not d["what_it_is"].strip():
        raise ValueError("what_it_is must be non-empty text")
    return Draft(Summary(*(" ".join(s[k].split()) for k in ("what", "why_now", "meaning"))),
                 _claims(d.get("why_now"), "why_now"), d["what_it_is"].strip(),
                 _claims(d.get("comparison"), "comparison"), _claims(d.get("use_cases"), "use_cases"),
                 _claims(d.get("risks"), "risks"))


class CardWriter:
    def __init__(self, llm: LLMClient, *, effort: str = EFFORT, max_tokens: int = MAX_TOKENS,
                 names: Mapping[str, str] | None = None):
        self.llm = llm
        self.effort = effort
        self.max_tokens = max_tokens
        self.names = dict(names or {})
        self.system = PROMPT_FILE.read_text(encoding="utf-8")
        self.prompt_hash = hashlib.sha256(self.system.encode("utf-8")).hexdigest()[:16]

    @property
    def fingerprint(self) -> str:
        return f"{self.prompt_hash}:{self.llm.model}:{self.effort}"

    def request(self, ci: CardInput, *, error: str = "") -> LLMRequest:
        user = user_message(ci, self.names)
        if error:
            user += (f"\n\nYour previous answer was rejected: {error}. "
                     "Answer again in the required JSON shape.")
        return LLMRequest(system=self.system, user=user, max_tokens=self.max_tokens, effort=self.effort,
                          schema=SCHEMA, purpose="card")

    def draft(self, ci: CardInput) -> Draft:
        """한 번 묻고, 형식이 틀리면 무엇이 틀렸는지 알려 한 번 더 묻는다. 예산 초과는 그대로 올린다."""
        error = ""
        for _ in (1, 2):
            resp = self.llm.complete(self.request(ci, error=error))
            if resp.stop_reason == "refusal":
                raise CardError("refusal")
            if resp.stop_reason == "max_tokens":
                raise CardError("max_tokens — 출력 한도에 걸려 JSON 이 잘렸다")
            try:
                return parse_draft(resp.text)
            except ValueError as e:
                error = str(e)
        raise CardError(f"형식 오류 두 번: {error}")


# --- 렌더 ---


@dataclass
class Card:
    markdown: str
    gate: gate.GateResult
    draft: Draft


def _label(d: ev.Evidence) -> str:
    if d.source == "github":
        return "GitHub 릴리스" if d.kind == "release" else "GitHub"
    if d.source == "hn":
        return "HN 댓글" if d.kind == "comment" else "HN"
    if d.source == "geeknews":
        return "GeekNews"
    if d.source == "package":
        return d.title
    return urlsplit(d.url).netloc.removeprefix("www.")


def _links(c: Claim, by_id: Mapping[str, ev.Evidence]) -> str:
    docs = [by_id[s] for s in c.sources if s in by_id]
    return " · ".join(f"[{_label(d)}]({d.url})" for d in docs)


def _claim_line(c: Claim, by_id: Mapping[str, ev.Evidence], *, with_date: bool = False) -> str:
    parts = ["-"]
    if with_date and c.date:
        parts.append(c.date)
    if c.repo and _REPO_RE.match(c.repo):
        parts.append(f"[{c.repo}](https://github.com/{c.repo}) —")
    parts.append(c.text)
    links = _links(c, by_id)
    if links:
        parts.append(links)
    parts.append(f"({c.basis})")
    return " ".join(parts)


def _num(n: Any) -> str:
    return f"{int(n):,}" if isinstance(n, (int, float)) else "—"


def _numbers(ci: CardInput, names: Mapping[str, str]) -> list[str]:
    e, t = ci.entry, ci.target
    rows = [("누적 스타", f"{_num(e.get('stars_end'))} ({t.until.isoformat()} 기준)"),
            ("이번 주 증가", f"+{_num(e.get('gain'))}")]
    if e.get("start_stars"):
        rows.append(("성장률", f"{float(e.get('gain', 0)) / float(e['start_stars']):+.0%} "
                               f"(주 시작 {_num(e['start_stars'])})"))
    rows.append(("AI 탭 순위", " · ".join(f"{AXIS_LABEL[a]} {r}위" for a, r in ci.ranks) or "—"))
    days = e.get("days")
    if e.get("exact") and days:
        rows.append(("일별 증가", " · ".join(f"{(t.since + timedelta(days=i)).strftime('%m-%d')} +{_num(n)}"
                                            for i, n in enumerate(days))))
    def why(s: Spike) -> str:
        return f"평소의 {s.ratio:,.0f}배" if s.baseline > 0 else "이전 기록 0 — 공개·출시 무렵"

    rows.append(("급등일", " · ".join(f"{_fmt_spike(s)} ({why(s)})" for s in ci.spikes) or "없음"))
    cat, sec = e.get("category"), e.get("secondary")
    label = f"{e.get('type') or '—'} · {names.get(cat, cat) if cat else '—'}"
    if sec:
        label += f" (보조: {names.get(sec, sec)})"
    rows.append(("유형 · 카테고리", label))
    rows.append(("확인 필요", " · ".join(f["label"] for f in e.get("flags") or []) or "없음"))
    return ["| 항목 | 값 |", "|---|---|", *(f"| {k} | {v} |" for k, v in rows)]


def _facts(ci: CardInput) -> list[str]:
    repo = next((d.extra for d in ci.docs if d.source == "github" and d.kind == "repo"), {})
    rows: list[tuple[str, str]] = [("라이선스", str(repo.get("license") or "없음·모름"))]
    rows.append(("기여자", _num(repo.get("contributors"))))
    share = repo.get("top_contributor_share")
    rows.append(("상위 1명 기여 비중", f"{share:.0%}" if isinstance(share, (int, float)) else "—"))
    if repo.get("issues_enabled") is False:
        rows.append(("지난 30일 이슈", "이슈 꺼짐"))
    else:
        rows.append(("지난 30일 이슈", f"열림 {_num(repo.get('issues_opened_30d'))} · "
                                      f"닫힘 {_num(repo.get('issues_closed_30d'))}"))
    cad = repo.get("release_cadence_days")
    rows.append(("릴리스 주기", f"약 {cad:g}일마다" if isinstance(cad, (int, float)) else "릴리스 없음·모름"))
    rows.append(("열린 이슈+PR", _num(repo.get("open_issues"))))
    for d in ci.docs:
        if d.source == "package":
            x = d.extra
            rows.append(("패키지", f"{d.title} — 지난 주 다운로드 {_num(x.get('downloads_last_week'))} · "
                                   f"패키지 의존 저장소 {_num(x.get('dependent_repos'))} — "
                                   f"출처 {x.get('attribution')}"))
    return ["| 항목 | 값 |", "|---|---|", *(f"| {k} | {v} |" for k, v in rows)]


def _body(ci: CardInput, dr: Draft, names: Mapping[str, str], generated: date) -> str:
    by_id = {f"E{i}": d for i, d in enumerate(ci.docs, 1)}
    t = ci.target
    cited = sorted({s for c in (*dr.why_now, *dr.comparison, *dr.use_cases, *dr.risks)
                    for s in c.sources if s in by_id}, key=lambda s: int(s[1:]))
    lines = [f"# {t.full_name}", "",
             "## ① 3줄 요약", f"- **무엇인지** — {dr.summary.what}",
             f"- **왜 지금 떴나** — {dr.summary.why_now}", f"- **어떤 의미인지** — {dr.summary.meaning}", "",
             "## ② 숫자", *_numbers(ci, names), "",
             "## ③ 왜 지금 떴나", *(_claim_line(c, by_id, with_date=True) for c in dr.why_now), "",
             "## ④ 무엇인가", dr.what_it_is, "",
             "## ⑤ 비교", *(_claim_line(c, by_id) for c in dr.comparison), "",
             "## ⑥ 활용사례", *(_claim_line(c, by_id) for c in dr.use_cases), "",
             "## ⑦ 한계·리스크", *_facts(ci), "", *(_claim_line(c, by_id) for c in dr.risks), "",
             "## ⑧ 변경 기록",
             f"- {generated.isoformat()} 처음 작성 — 기준일 {t.until.isoformat()} · "
             f"근거 {len(ci.docs)}건", "",
             "## 근거"]
    for s in cited:
        d = by_id[s]
        title = re.sub(r"[\[\]\n]", " ", d.title).strip() or d.url
        day = f" · {d.published_at[:10]}" if d.published_at else ""
        lines.append(f"- {s} [{title}]({d.url}) — {_label(d)}{day}")
    if ci.failed_sources:
        lines += ["", f"수집 실패: {' · '.join(ci.failed_sources)} — 이 출처의 근거는 이번 주 카드에 없다."]
    return "\n".join(lines) + "\n"


def _fill_empty(body: str) -> str:
    """게이트를 지나 비어 버린 인용 섹션에 "근거가 있는 항목이 없다"를 적는다.

    목록 항목이 아니라 문단이라 게이트의 "출처 없음" 대상이 아니다(게이트를 다시 돌려도 그대로다).
    """
    out: list[str] = []
    parts = re.split(r"(?m)^(## .*)$", body)
    out.append(parts[0])
    for head, text in zip(parts[1::2], parts[2::2], strict=True):
        name = head[3:]
        if name.startswith(gate.CARD_CITED) and not re.search(r"(?m)^\s*- ", text):
            text = f"\n{NO_ITEMS}\n" + text.lstrip("\n")
            text = text if text.endswith("\n\n") else text + "\n"
        out.append(head + text)
    return "".join(out)


def render_card(ci: CardInput, dr: Draft, *, names: Mapping[str, str], verified_repos: Sequence[str],
                fingerprint: str, generated: date) -> Card:
    body = _body(ci, dr, names, generated)
    res = gate.check(body, [d.url for d in ci.docs], repos=[ci.target.full_name, *verified_repos],
                     cited=gate.CARD_CITED)
    t = ci.target
    front = ["---", f"repo: {t.full_name}", f"repo_id: {t.repo_id}", f"week: {t.since.isoformat()}",
             f"as_of: {t.until.isoformat()}", f"generated: {generated.isoformat()}",
             f"fingerprint: {fingerprint}", f"evidence: {len(ci.docs)}", f"gate_checked: {res.checked}",
             f"gate_excluded: {len(res.excluded)}", "---", ""]
    return Card("\n".join(front) + _fill_empty(res.body), res, dr)


# --- 실행 ---


def card_dir(work_dir: Path, week_start: date) -> Path:
    return ev.week_dir(work_dir, week_start) / "cards"


def _slug(full_name: str) -> str:
    return full_name.replace("/", "__")


def run_analyze(writer: CardWriter, inputs: Sequence[CardInput], *, work_dir: Path, week_start: date,
                names: Mapping[str, str], repo_exists: Callable[[str], bool], today: date,
                log: Callable[[str], None] = print) -> dict[str, Any]:
    out_dir = card_dir(work_dir, week_start)
    stats: dict[str, Any] = {"cards": 0, "failed": [], "excluded_claims": 0, "stopped": None}
    for i, ci in enumerate(inputs, 1):
        name = ci.target.full_name
        try:
            dr = writer.draft(ci)
        except BudgetExceeded as e:
            stats["stopped"] = "budget"
            log(f"  예산 상한 — 여기서 멈춘다: {e}")
            break
        except CardError as e:
            stats["failed"].append(name)
            log(f"  [{i}/{len(inputs)}] {name}: 카드 실패 — {e}")
            continue
        candidates = {c.repo for c in dr.comparison if c.repo and _REPO_RE.match(c.repo)
                      and c.repo.lower() != name.lower()}
        verified = [r for r in sorted(candidates) if repo_exists(r)]
        card = render_card(ci, dr, names=names, verified_repos=verified, fingerprint=writer.fingerprint,
                           generated=today)
        slug = _slug(name)
        io.write_text_atomic(out_dir / f"{slug}.md", card.markdown)
        io.write_json(out_dir / f"{slug}.gate.json",
                      {"repo": name, "checked": card.gate.checked, "kept_links": card.gate.kept_links,
                       "excluded": card.gate.log(), "verified_repos": verified,
                       "unverified_repos": sorted(candidates - set(verified))})
        io.write_json(out_dir / f"{slug}.draft.json", asdict(dr))
        stats["cards"] += 1
        stats["excluded_claims"] += len(card.gate.excluded)
        log(f"  [{i}/{len(inputs)}] {name}: 카드 작성 — 게이트 제외 {len(card.gate.excluded)}건")
    return stats


def dry_run(writer: CardWriter, inputs: Sequence[CardInput], *, batch: bool = False) -> dict[str, Any]:
    """호출 0 — 실제로 보낼 요청을 만들어 입력 토큰을 재고 비용 범위를 낸다(FR-6.6)."""
    typ = cons = 0
    for ci in inputs:
        req = writer.request(ci)
        typ += request_tokens(req.system, req.user, schema=True, typical=True)
        cons += request_tokens(req.system, req.user, schema=True)
    n = len(inputs)
    lo = cost(MODEL, Usage(typ, TYPICAL_OUTPUT * n), batch=batch)
    hi = cost(MODEL, Usage(cons, writer.max_tokens * n), batch=batch)
    return {"cards": n, "llm_calls": n, "repos": [ci.target.full_name for ci in inputs],
            "input_tokens": [typ, cons], "total_usd": [round(lo, 4), round(hi, 4)],
            "per_card_usd": [round(lo / n, 4), round(hi / n, 4)] if n else [0, 0],
            "assumptions": {"model": MODEL, "effort": writer.effort, "batch": batch,
                            "output_tokens": [TYPICAL_OUTPUT, writer.max_tokens],
                            "retry": "형식 오류면 한 번 더 — 그때는 2배"},
            "fingerprint": writer.fingerprint}
