"""블로그 초안 (SPEC FR-16, 결정 36·37·39·59·60) — 과금 단계(주 1회 호출). dry-run 이 먼저다.

- 글 구성(결정 60, 2026-10-29 사용자): 지금 뜨는 저장소의 흐름 개괄 → **TOP 10 저장소마다 1. 무엇인가 ·
  2. 왜 지금 떴나 · 3. 활용 사례**(저장소 하나에 한글 500자 안팎) → 주의할 점 · 한 장 요약 · 다음 글 예고.
  대표 이미지는 저장소 소셜 미리보기(주인이 올린 것), 없으면 LLM 이 쓴 생성 프롬프트.
- 고정 틀은 코드가 채운다(견본 `docs/ref/blog-sample.md`, 결정 39) — 제목(이모지 + 시리즈 + 회차 + 핵심 3개),
  시리즈 소개, 정보 블록(⭐ 줄), TOP 숫자 목록, 함께 보기(▶), 글 모음, 해시태그.
- LLM 은 정해진 JSON 으로 글만 쓴다. 출처는 번호(R1 · R1:E3)로만 가리키고 링크는 코드가 만든다(FR-16.2) —
  인용 게이트를 지난다. 형식 검사기(check_draft)가 막는다: 글 안의 URL·마크다운 기호, 목록 밖 출처,
  출처 없는 주장, 입력에 없는 숫자(FR-6.5), 합쇼체가 아닌 문장(FR-16.6), TOP 순서, 분량. 걸리면 이유를 붙여
  한 번 다시 묻는다.
- 결과는 `.work/<주>/blog/`(결정 59 — 공개 저장소에 올리지 않는다). Notion 에는 `notion --run` 이 올린다.
"""

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from startrend import gate
from startrend.budget import BudgetExceeded
from startrend.clients.llm import LLMClient, LLMRequest, Usage, cost, request_tokens
from startrend.core import cards, io, untrusted

PROMPT_FILE = Path(__file__).resolve().parents[1] / "prompts" / "blog.md"
MODEL = "claude-opus-5-5"
EFFORT = "medium"
MAX_TOKENS = 32_000          # 사고 + JSON — 16,000 은 실측에서 모자랐다(MEASURE §27). 스트리밍으로 받는다
TYPICAL_OUTPUT = 8_000       # dry-run 하한 가정 — 첫 실행으로 실측

SERIES = "깃허브 AI 트렌드 주간 동향"        # 2026-10-26 사용자 결정 (FR-16.8)
SERIES_START = date(2026, 10, 18)           # 1회 주
EMOJI = "🤖"
REPO_URL = "https://github.com/daehyub71/github-ai-star-trend"
CHANNEL = ("백발개발자의 바이브코딩", "https://www.youtube.com/@50VibeLog")
SERIES_TAGS = ("#깃허브AI트렌드", "#GitHub트렌드", "#AI트렌드", "#오픈소스", "#AI코딩")
CHANNEL_TAGS = ("#백발개발자", "#바이브코딩", "#오십로그", "#50Log", "#오십바이브로그", "#50바이브로그",
                "#50VibeLog")                # 견본 끝줄의 고정 채널 태그 (FR-16.8)
TOP_N = 10
CARD_SECTIONS = ("① 3줄 요약", "③ 왜 지금 떴나", "④ 무엇인가", "⑥ 활용사례")
PARTS = (("what", "무엇인가"), ("why_now", "왜 지금 떴나"), ("use_cases", "활용 사례"))
REPO_CHARS = (350, 750)      # 저장소 하나의 세 부분 합 — 사용자 "한글 500자 정도"
SMALL = {str(n) for n in range(0, 11)}       # 셈말로 쓰는 작은 수는 허용
SCENE_MIN = 400              # 그림 장면 프롬프트 최소 글자 수 — 구도·요소·라벨 자리까지 쓰게(결정 60)
LABELS = (2, 6)              # 그림에 나중에 얹을 한글 라벨 수
LABEL_MAX = 12
# 블로그 그림 공통 스타일 — 코드가 모든 장면 뒤에 붙여 한 세트로 보이게 한다
# (사이트 아트의 공통 문단과 같은 방식)
STYLE = ("Style: clean educational explainer illustration for a beginner-friendly tech blog, "
         "flat vector with soft drop shadows, warm off-white background (#F7F4EE), "
         "limited palette of deep navy (#1F2A44), teal (#2A9D8F), coral (#E76F51) and mustard (#E9C46A), "
         "thick rounded outlines, friendly simple shapes, generous white space, 16:9 landscape (1600x900). "
         "Leave every label tag empty so Korean labels can be added later. "
         "No text, no letters, no numbers, no logos, no brand marks, no real app screenshots, "
         "no human faces.")
WEEKDAY = "월화수목금토일"


class BlogError(Exception):
    pass


def episode(week: str) -> int:
    return (date.fromisoformat(week) - SERIES_START).days // 7 + 1


# --- 입력 ---


@dataclass(frozen=True)
class BlogRepo:
    ref: str
    rank: int
    repo_id: int
    full_name: str
    category: str
    facts: tuple[str, ...]           # 코드가 쓴 순위·숫자 줄
    card: str                        # 블로그에 쓰는 카드 섹션 — 링크를 출처 번호로 바꿈


@dataclass(frozen=True)
class BlogInput:
    week: str
    until: str
    episode: int
    names: Mapping[str, str]
    briefing: str                    # 링크를 뺀 브리핑 본문
    top: tuple[Mapping[str, Any], ...]                    # 지금 뜨는 저장소(AI 탭) — 글에 쓰는 것
    repos: tuple[BlogRepo, ...]
    sources: Mapping[str, tuple[str, str]]                # 출처 번호 → (제목, URL)


def _lf(text: str) -> str:
    return text.replace("\r\n", "\n")


def _body(md: str) -> str:
    md = re.sub(r"^---\n.*?\n---\n", "", _lf(md), count=1, flags=re.S).lstrip("\n")
    return re.sub(r"^# [^\n]*\n+", "", md, count=1)


_LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
_BARE = re.compile(r"https?://\S+|www\.\S+")
_EVIDENCE = re.compile(r"(?m)^- (E\d+) \[(.*?)\]\((\S+?)\)")


def _fmt(n: Any) -> str:
    return f"{n:,}" if isinstance(n, int) else "—"


def _cat(e: Mapping[str, Any], names: Mapping[str, str]) -> str:
    cat = e.get("category")
    return names.get(cat, cat) if cat else "AI"


def _fact(e: Mapping[str, Any], names: Mapping[str, str]) -> str:
    g = e.get("growth")
    pct = f" · 주 시작 대비 +{g * 100:.1f}%" if isinstance(g, (int, float)) else ""
    return (f"지금 뜨는 저장소 {e.get('rank')}위 {e['full_name']} — 지난 주 +{_fmt(e.get('gain'))} · "
            f"누적 {_fmt(e.get('stars_end'))}{pct} · 생성 {e.get('created')} · {_cat(e, names)}")


def _convert_card(md: str, ref: str, full_name: str, sources: dict[str, tuple[str, str]]) -> str:
    """블로그에 쓰는 섹션만, 링크는 출처 번호로 — LLM 은 URL 을 보지 않는다."""
    body = _body(md)
    by_url: dict[str, str] = {}
    for eid, title, url in _EVIDENCE.findall(body):
        sid = f"{ref}:{eid}"
        sources[sid] = (" ".join(title.split()), url)
        by_url.setdefault(url, sid)
    repo_url = f"https://github.com/{full_name}"

    def sub(m: re.Match[str]) -> str:
        text, url = m.group(1), m.group(2)
        if url in by_url:
            return f"{text} [{by_url[url]}]"
        if url.rstrip("/") == repo_url:
            return f"{text} [{ref}]"
        return text

    secs = cards.sections(body)
    parts = [f"## {h}\n{secs[h].strip()}" for h in CARD_SECTIONS if h in secs]
    return _BARE.sub("(링크)", _LINK.sub(sub, "\n\n".join(parts))).strip()


def load_input(site_dir: Path, private_dir: Path, week: str) -> BlogInput:
    wfile = site_dir / "weeks" / f"{week}.json"
    if not wfile.exists():
        raise FileNotFoundError(f"사이트 데이터가 없다 — export 를 먼저: {wfile}")
    names = {c["id"]: c["name"] for c in io.read_json(site_dir / "index.json").get("categories", [])}
    data = io.read_json(wfile)
    gain = list(((data.get("axes") or {}).get("gain") or {}).get("ai") or [])
    ref_file = private_dir / "cards" / "index.json"
    slugs = {int(r["repo_id"]): r["slug"] for r in (io.read_json(ref_file) if ref_file.exists() else [])}
    sources: dict[str, tuple[str, str]] = {}
    repos: list[BlogRepo] = []
    top: list[Mapping[str, Any]] = []
    for e in gain:
        if len(repos) >= TOP_N:
            break
        rid = int(e["id"])
        p = private_dir / "cards" / f"{slugs[rid]}.md" if rid in slugs else None
        if p is None or not p.exists():
            continue
        ref, name = f"R{len(repos) + 1}", e["full_name"]
        sources[ref] = (name, f"https://github.com/{name}")
        card = _convert_card(_lf(io.read_text(p)), ref, name, sources)
        repos.append(BlogRepo(ref, int(e.get("rank") or 0), rid, name, _cat(e, names), (_fact(e, names),),
                              card))
        top.append(e)
    bpath = private_dir / "briefings" / f"{week}.md"
    briefing = _BARE.sub("", _LINK.sub(r"\1", _body(io.read_text(bpath)))).strip() if bpath.exists() else ""
    return BlogInput(week, data.get("week_end", ""), episode(week), names, briefing, tuple(top), tuple(repos),
                     sources)


def _kdate(d: str, *, year: bool) -> str:
    x = date.fromisoformat(d)
    return f"{f'{x.year}년 ' if year else ''}{x.month}월 {x.day}일({WEEKDAY[x.weekday()]})"


def user_message(bi: BlogInput) -> str:
    facts = [f"series: {SERIES} · episode {bi.episode}",
             f"week: {_kdate(bi.week, year=True)} ~ {_kdate(bi.until, year=False)} (UTC)",
             f"TOP {len(bi.repos)} rising AI repositories (numbers computed by code):"]
    facts += [r.facts[0] for r in bi.repos]
    if bi.briefing:
        facts += ["", "weekly briefing (already published on the site):", bi.briefing]
    items = [f"[{r.ref}] {r.full_name} · {r.category}\n" + "\n".join(r.facts) +
             f"\ncard (sources marked like [{r.ref}:E3]):\n{r.card}" for r in bi.repos]
    doc = untrusted.block("document", "\n".join(facts))
    return f"{doc}\n{untrusted.block('evidence', chr(10).join(items))}"


# --- 출력 ---


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


_STR = {"type": "string"}
_STRS = {"type": "array", "items": _STR}
_CLAIM = _obj({"text": _STR, "sources": _STRS})
_IDEA = _obj({"teaches": _STR, "scene": _STR, "labels": _STRS})
SCHEMA: dict[str, Any] = _obj({
    "title_points": _STRS,
    "intro": _STR,
    "overview": _obj({"heading": _STR, "paras": {"type": "array", "items": _CLAIM}}),
    "repos": {"type": "array", "items": _obj({"ref": _STR, "subtitle": _STR, "what": _CLAIM,
                                              "why_now": _CLAIM, "use_cases": _CLAIM, "image": _IDEA})},
    "cover": _IDEA,
    "misreadings": {"type": "array", "items": _obj({"claim": _STR, "answer": _STR})},
    "summary": _STR,
    "next": _STR,
    "tags": _STRS,
})


@dataclass(frozen=True)
class Claim:
    text: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class ImageIdea:
    """교육용 그림 — 가르칠 것(한국어) · 장면 프롬프트(영어, 스타일 문단은 코드가 붙인다) · 얹을 한글 라벨."""
    teaches: str
    scene: str
    labels: tuple[str, ...]

    def prompt(self) -> str:
        return f"{self.scene}\n\n{STYLE}"


@dataclass(frozen=True)
class RepoPost:
    ref: str
    subtitle: str
    what: Claim
    why_now: Claim
    use_cases: Claim
    image: ImageIdea


@dataclass(frozen=True)
class BlogDraft:
    title_points: tuple[str, ...]
    intro: str
    overview_heading: str
    overview: tuple[Claim, ...]
    repos: tuple[RepoPost, ...]
    cover: ImageIdea
    misreadings: tuple[tuple[str, str], ...]
    summary: str
    next: str
    tags: tuple[str, ...]


def _str(v: Any, name: str) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"{name} must be non-empty text")
    return " ".join(v.split())


def _strs(v: Any, name: str) -> tuple[str, ...]:
    if not isinstance(v, list):
        raise ValueError(f"{name} must be a list")
    return tuple(_str(x, name) for x in v)


def _claim(v: Any, name: str) -> Claim:
    if not isinstance(v, dict):
        raise ValueError(f"{name} must be an object with text and sources")
    return Claim(_str(v.get("text"), f"{name}.text"), _strs(v.get("sources") or [], f"{name}.sources"))


def _idea(v: Any, name: str) -> ImageIdea:
    if not isinstance(v, dict):
        raise ValueError(f"{name} must be an object with teaches, scene and labels")
    return ImageIdea(_str(v.get("teaches"), f"{name}.teaches"), _str(v.get("scene"), f"{name}.scene"),
                     _strs(v.get("labels") or [], f"{name}.labels"))


def parse_blog(text: str) -> BlogDraft:
    try:
        d = json.loads(text)
    except ValueError as e:
        raise ValueError(f"not JSON ({e})") from e
    if not isinstance(d, dict):
        raise ValueError("answer must be a JSON object")
    points = _strs(d.get("title_points"), "title_points")
    if len(points) != 3:
        raise ValueError(f"title_points needs exactly 3 items, got {len(points)}")
    ov = d.get("overview")
    if not isinstance(ov, dict) or not isinstance(ov.get("paras"), list):
        raise ValueError("overview needs heading and paras")
    repos = []
    for r in d.get("repos") or []:
        if not isinstance(r, dict):
            raise ValueError("repos items must be objects")
        repos.append(RepoPost(_str(r.get("ref"), "ref"), _str(r.get("subtitle"), "subtitle"),
                              what=_claim(r.get("what"), "what"),
                              why_now=_claim(r.get("why_now"), "why_now"),
                              use_cases=_claim(r.get("use_cases"), "use_cases"),
                              image=_idea(r.get("image"), "image")))
    myths = []
    for m in d.get("misreadings") or []:
        if not isinstance(m, dict):
            raise ValueError("misreadings items need claim and answer")
        myths.append((_str(m.get("claim"), "claim"), _str(m.get("answer"), "answer")))
    return BlogDraft(points, _str(d.get("intro"), "intro"), _str(ov.get("heading"), "overview.heading"),
                     tuple(_claim(p, "overview.paras") for p in ov["paras"]), tuple(repos),
                     _idea(d.get("cover"), "cover"), tuple(myths),
                     _str(d.get("summary"), "summary"), _str(d.get("next"), "next"),
                     _strs(d.get("tags") or [], "tags"))


_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_URLISH = re.compile(r"(?i)https?://|www\.|\.com/|\.io/")
_MARKDOWN = re.compile(r"\*\*|`|\]\(|^\s*#|^\s*[-*] |\[[^\]]*\]")
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]")


def _numbers(text: str) -> set[str]:
    return {t.replace(",", "") for t in _NUM.findall(text)}


def check_draft(dr: BlogDraft, bi: BlogInput) -> list[str]:
    """형식 검사기 — 빈 목록이면 통과. 메시지는 LLM 에게 다시 물을 때 그대로 붙인다."""
    errors: list[str] = []
    allowed = _numbers(user_message(bi)) | SMALL | {str(bi.episode)}
    claims: list[tuple[str, Claim]] = [(f"overview para {i + 1}", c) for i, c in enumerate(dr.overview)]
    want = [r.ref for r in bi.repos]
    got = [r.ref for r in dr.repos]
    if got != want:
        errors.append(f"repos 순서 — write exactly {want} in this order (got {got})")
    for r in dr.repos:
        claims += [(f"{r.ref} {label}", getattr(r, key)) for key, label in PARTS]
        n = sum(len(getattr(r, key).text) for key, _ in PARTS)
        if not REPO_CHARS[0] <= n <= REPO_CHARS[1]:
            errors.append(f"{r.ref} 분량 — 세 부분 합 {n}자, 저장소 하나에 한글 500자 안팎"
                          f"({REPO_CHARS[0]}~{REPO_CHARS[1]}자)")
    texts: list[tuple[str, str]] = [("title_points", t) for t in dr.title_points]
    texts += [("intro", dr.intro), ("summary", dr.summary), ("next", dr.next),
              ("heading", dr.overview_heading)]
    texts += [("tags", t) for t in dr.tags] + [(f"{r.ref} subtitle", r.subtitle) for r in dr.repos]
    texts += [("misreadings", f"{c} {a}") for c, a in dr.misreadings]
    texts += [(where, c.text) for where, c in claims]
    for where, c in claims:
        if not c.sources:
            errors.append(f"{where}: 출처 없는 주장 — every paragraph needs source ids")
        for sid in c.sources:
            if sid not in bi.sources:
                errors.append(f"{where}: {sid} 는 목록에 없는 출처 — use only ids shown in <evidence>")
    for where, idea in [("cover", dr.cover)] + [(f"{r.ref} image", r.image) for r in dr.repos]:
        if _URLISH.search(idea.scene):
            errors.append(f"{where}: URL 을 쓰지 않는다")
        if len(idea.scene) < SCENE_MIN:
            errors.append(f"{where}: 그림 프롬프트가 짧다({len(idea.scene)}자) — "
                          f"가르칠 개념의 단계·비유·구도·요소·빈 라벨 자리까지 {SCENE_MIN}자 이상으로")
        if not LABELS[0] <= len(idea.labels) <= LABELS[1]:
            errors.append(f"{where}: 라벨은 {LABELS[0]}~{LABELS[1]}개")
        for label in idea.labels:
            if len(label) > LABEL_MAX or "·" in label:
                errors.append(f"{where}: 라벨 '{label}' 은 {LABEL_MAX}자 이내, 가운뎃점 없이")
        texts += [(f"{where} teaches", idea.teaches)] + [(f"{where} label", lb) for lb in idea.labels]
    for where, t in texts:
        if _URLISH.search(t):
            errors.append(f"{where}: URL 을 쓰지 않는다 — cite sources by id only")
        if _MARKDOWN.search(t):
            errors.append(f"{where}: 마크다운 기호(**, `, #, [ ], 목록 표시)를 쓰지 않는다 — plain text only")
        for num in sorted(_numbers(t) - allowed):
            errors.append(f"{where}: 입력에 없는 숫자 {num} — use only numbers given in the input")
    polite =[("intro", dr.intro), ("summary", dr.summary), ("next", dr.next)]
    polite += [(where, c.text) for where, c in claims] + [("misreadings", a) for _, a in dr.misreadings]
    for where, t in polite:
        sentences = [m.group(0).strip() for m in _SENTENCE.finditer(t)]
        plain = [s for s in sentences if re.search(r"(?<!니)다[.!]$", s)]
        if sentences and len(plain) / len(sentences) > 0.3:
            errors.append(f"{where}: 합쇼체로 쓴다(~합니다/~입니다, 질문은 ~까요?) — "
                          + " / ".join(plain[:2]))
    if "?" not in dr.intro:
        errors.append("intro: 질문으로 여는 문단이어야 한다(물음표가 있어야 한다)")
    for p in dr.title_points:
        if "·" in p or len(p) > 30:
            errors.append(f"title_points '{p}': 30자 이내, 가운뎃점 없이")
    if len(dr.misreadings) < 3:
        errors.append("misreadings: 3개 이상")
    return list(dict.fromkeys(errors))


# --- 렌더 ---


def _tag(t: str) -> str:
    t = re.sub(r"[^0-9A-Za-z가-힣]", "", t.lstrip("#"))
    return f"#{t}" if t else ""


def _links(c: Claim, bi: BlogInput) -> str:
    out = []
    for sid in dict.fromkeys(c.sources):
        if sid in bi.sources:
            title, url = bi.sources[sid]
            title = re.sub(r"[\[\]]", " ", title).strip()
            out.append(f"[{title[:59] + '…' if len(title) > 60 else title}]({url})")
    return f" ({' · '.join(out)})" if out else ""


def _rank_line(e: Mapping[str, Any], names: Mapping[str, str]) -> str:
    name = e["full_name"]
    return (f"{e.get('rank')}위 [{name}](https://github.com/{name}) — 지난 주 +{_fmt(e.get('gain'))} 스타 · "
            f"누적 {_fmt(e.get('stars_end'))} · {_cat(e, names)}")


def title_of(bi: BlogInput, dr: BlogDraft) -> str:
    return f"{EMOJI} {SERIES} {bi.episode}회 {EMOJI} " + " · ".join(dr.title_points)


def _heading(r: BlogRepo, p: RepoPost) -> str:
    return f"{r.rank}위 {r.full_name} — {p.subtitle}"


def _slot(what: str, idea: ImageIdea) -> list[str]:
    """그림이 들어갈 자리 — 가르칠 것 · 얹을 라벨 한 줄 + 복사해 쓰는 프롬프트(코드 블록)."""
    return [f"> 🎨 {what} — {idea.teaches} · 얹을 라벨: {' · '.join(idea.labels)}",
            f"```text\n{idea.prompt()}\n```"]


def render(bi: BlogInput, dr: BlogDraft, *, published: Sequence[tuple[int, str, str]],
           images: Mapping[str, str]) -> tuple[str, str, gate.GateResult]:
    """(제목, 본문 마크다운, 게이트 결과). 소제목은 ### · 주소는 링크(FR-16.5 ④ — R22 시험 B)."""
    n = bi.episode
    posts = {p.ref: p for p in dr.repos}
    out: list[str] = [
        *_slot("대표 이미지 자리", dr.cover),
        f"「{SERIES}」의 {n}번째 글입니다. 매주 GitHub 에서 스타가 가장 많이 늘어난 AI 저장소를 "
        "숫자와 근거로 정리합니다.", dr.intro, f"***{SERIES} {n}회 정보***",
        f"⭐ 이 글의 내용 : 이번 주 흐름 한눈에 · TOP {len(bi.repos)} 저장소"
        "(무엇인가 · 왜 지금 떴나 · 활용 사례) · 숫자를 읽을 때 주의할 점 · 한 장 요약",
        f"⭐ 집계 기간 : {_kdate(bi.week, year=True)} ~ {_kdate(bi.until, year=False)}, UTC 기준",
        "⭐ 데이터 기준 : 스타 1,000개 이상 저장소 전체 스냅샷과 상위 후보의 일별 스타 · "
        "AI 여부와 카테고리는 Claude 가 판정 · 숫자는 GitHub API 값을 코드가 계산",
        "⭐ 쓰는 방식 : 숫자와 링크는 코드가, 글 초안은 AI(Claude)가 쓰고 사람이 검토합니다",
        f"⭐ 데이터 저장소 : [{REPO_URL}]({REPO_URL})",
        f"### 이번 주 흐름 — {dr.overview_heading}"]
    out += [f"{c.text}{_links(c, bi)}" for c in dr.overview]
    out.append(f"### TOP {len(bi.repos)} — 지금 뜨는 AI 저장소")
    out += [_rank_line(e, bi.names) for e in bi.top]
    for r in bi.repos:
        p = posts.get(r.ref)
        if p is None:
            continue
        out.append(f"### {_heading(r, p)}")
        if r.full_name in images:
            out += [f"![{r.full_name} 대표 이미지]({images[r.full_name]})",
                    f"이미지: {r.full_name} 저장소의 소셜 미리보기"]
        else:
            out += _slot("그림 자리", p.image)
        out += [f"{i}. {label} — {getattr(p, key).text}{_links(getattr(p, key), bi)}"
                for i, (key, label) in enumerate(PARTS, 1)]
    out.append("### 이번 주 숫자를 읽을 때 주의할 점")
    out += [f"{c} — {a}" for c, a in dr.misreadings]
    out += ["### 한 장 요약", dr.summary, dr.next, "### 함께 보기",
            f"▶ 데이터 저장소(GitHub) : [{REPO_URL}]({REPO_URL})",
            f"▶ 채널 : {CHANNEL[0]} [{CHANNEL[1]}]({CHANNEL[1]})", f"### {SERIES} 글 모음"]
    out += [f"▶ {k}회 {t} : [{u}]({u})" for k, t, u in published if k != n]
    out.append(f"▶ {n}회 {' · '.join(dr.title_points)} (이 글)")
    tags = [*SERIES_TAGS, *(_tag(t) for t in dr.tags), *CHANNEL_TAGS]
    out.append(" ".join(t for t in dict.fromkeys(tags) if t))
    body = "\n\n".join(out) + "\n"
    urls = [u for _, u in bi.sources.values()] + [REPO_URL, CHANNEL[1]] + [u for _, _, u in published]
    res = gate.check(body, urls + list(images.values()), repos=[r.full_name for r in bi.repos])
    return title_of(bi, dr), res.body, res


def images_doc(bi: BlogInput, dr: BlogDraft, *, images: Mapping[str, str], files: Mapping[str, str]) -> str:
    """사진 배치 문서(FR-16.7) — 소제목 → 이미지, 생성 프롬프트, 대표 이미지."""
    posts = {p.ref: p for p in dr.repos}
    rows = ["| (머리말) | 대표 이미지 — 생성 프롬프트 0 |", f"| 이번 주 흐름 — {dr.overview_heading} | — |"]

    def block(head: str, idea: ImageIdea) -> list[str]:
        return [f"### {head}", "", f"- 가르칠 것: {idea.teaches}",
                f"- 얹을 라벨: {' · '.join(idea.labels)}", "", "```text", idea.prompt(), "```", ""]

    prompts = block("0. 대표 이미지(글 맨 위)", dr.cover)
    alternatives: list[str] = []
    for r in bi.repos:
        p = posts.get(r.ref)
        if p is None:
            continue
        if r.full_name in images:
            where = f"{files[r.full_name]} (저장소 소셜 미리보기)" if r.full_name in files \
                else f"{images[r.full_name]} (저장소 소셜 미리보기)"
            alternatives += block(f"(대안) {r.rank}. {r.full_name} — 소셜 미리보기 대신 교육용 그림을 쓸 때",
                                  p.image)
        else:
            where = f"생성 프롬프트 {r.rank}"
            prompts += block(f"{r.rank}. {r.full_name}", p.image)
        rows.append(f"| {_heading(r, p)} | {where} |")
    return "\n".join([
        f"# {title_of(bi, dr)} — 사진 배치 참고", "",
        "> 본문: `post.md` · 이미지: `img/`(저장소 소셜 미리보기를 받아 둔 것). "
        "없는 자리는 아래 생성 프롬프트로 만든다.",
        "", "## 글", "", "| 소제목 | 이미지 |", "|---|---|", *rows, "",
        "## 생성 프롬프트 — 교육용 설명 그림", "",
        "- 코드 블록을 통째로 복사해 이미지 생성 도구에 붙여 넣습니다. 끝의 스타일 문단은 모든 그림에 같아서 "
        "한 세트로 보입니다.",
        "- 그림의 빈 라벨 칸에 '얹을 라벨'을 나중에 글자로 얹습니다(생성 이미지의 글자는 깨집니다).",
        "- 결과가 마음에 들지 않으면 장면 문단만 고치고 스타일 문단은 그대로 둡니다.", "",
        *prompts, *alternatives,
        "## 참고", "",
        "- 소셜 미리보기는 저장소 주인이 링크 미리보기용으로 올린 그림입니다. "
        "글에 쓸 때 출처(저장소 이름)를 함께 적습니다.",
        "- 저장소 README 의 그림은 쓰지 않습니다(NFR-9).",
        "- 네이버 대표 이미지는 글자가 적은 그림을 씁니다 — 생성 프롬프트 0 을 권합니다.", ""])


# --- 실행 ---


class BlogWriter:
    def __init__(self, llm: LLMClient, *, effort: str = EFFORT, max_tokens: int = MAX_TOKENS):
        self.llm = llm
        self.effort = effort
        self.max_tokens = max_tokens
        self.system = PROMPT_FILE.read_text(encoding="utf-8")
        self.prompt_hash = hashlib.sha256(self.system.encode("utf-8")).hexdigest()[:16]

    @property
    def fingerprint(self) -> str:
        return f"{self.prompt_hash}:{self.llm.model}:{self.effort}"

    def request(self, bi: BlogInput, *, error: str = "") -> LLMRequest:
        user = user_message(bi)
        if error:
            user += (f"\n\nYour previous answer was rejected: {error}\n"
                     "Fix every point and answer again in the required JSON shape.")
        return LLMRequest(system=self.system, user=user, max_tokens=self.max_tokens, effort=self.effort,
                          schema=SCHEMA, purpose="blog")

    def draft(self, bi: BlogInput) -> BlogDraft:
        error = ""
        for _ in (1, 2):
            resp = self.llm.complete(self.request(bi, error=error))
            if resp.stop_reason == "refusal":
                raise BlogError("refusal")
            if resp.stop_reason == "max_tokens":
                raise BlogError("max_tokens — 출력 한도에 걸려 JSON 이 잘렸다")
            try:
                dr = parse_blog(resp.text)
            except ValueError as e:
                error = str(e)
                continue
            problems = check_draft(dr, bi)
            if not problems:
                return dr
            error = "; ".join(problems[:15])
        raise BlogError(f"형식 검사 두 번 실패: {error}")


def run_blog(writer: BlogWriter, bi: BlogInput, *, work_dir: Path, today: date,
             published: Sequence[tuple[int, str, str]], images: Mapping[str, str], files: Mapping[str, str],
             log: Callable[[str], None] = print) -> dict[str, Any]:
    out = work_dir / bi.week / "blog"
    stats: dict[str, Any] = {"written": False, "stopped": None, "error": None, "excluded": 0}
    try:
        dr = writer.draft(bi)
    except BudgetExceeded as e:
        stats["stopped"] = "budget"
        log(f"  예산 상한 — 블로그 초안을 쓰지 않는다: {e}")
        return stats
    except BlogError as e:
        stats["error"] = str(e)
        log(f"  블로그 초안 실패 — {e}")
        return stats
    io.write_json(out / "draft.json", asdict(dr))
    meta = {"week": bi.week, "episode": bi.episode, "generated": today.isoformat(),
            "fingerprint": writer.fingerprint, "top": [r.full_name for r in bi.repos],
            "images": dict(images), "files": dict(files)}
    return _write(out, bi, dr, meta, stats, published=published, log=log)


def _write(out: Path, bi: BlogInput, dr: BlogDraft, meta: dict[str, Any], stats: dict[str, Any], *,
           published: Sequence[tuple[int, str, str]], log: Callable[[str], None]) -> dict[str, Any]:
    images, files = meta.get("images") or {}, meta.get("files") or {}
    title, body, res = render(bi, dr, published=published, images=images)
    io.write_text_atomic(out / "post.md", f"# {title}\n\n{body}")
    io.write_text_atomic(out / "images.md", images_doc(bi, dr, images=images, files=files))
    io.write_json(out / "gate.json", {"checked": res.checked, "kept_links": res.kept_links,
                                      "excluded": res.log()})
    io.write_json(out / "meta.json", {**meta, "chars": len(body)})
    stats.update(written=True, excluded=len(res.excluded), file=str(out / "post.md"), title=title,
                 chars=len(body), images=len(images), prompts=len(bi.repos) - len(images) + 1)
    log(f"  블로그 초안 — {len(body):,}자 · 게이트 제외 {len(res.excluded)}건 · 대표 이미지 {len(images)}개")
    return stats


def load_draft(path: Path) -> BlogDraft:
    """저장한 draft.json(asdict 모양) → BlogDraft."""
    d = io.read_json(path)

    def claim(c: Mapping[str, Any]) -> Claim:
        return Claim(c["text"], tuple(c["sources"]))

    def idea(i: Mapping[str, Any]) -> ImageIdea:
        return ImageIdea(i["teaches"], i["scene"], tuple(i["labels"]))

    return BlogDraft(tuple(d["title_points"]), d["intro"], d["overview_heading"],
                     tuple(claim(c) for c in d["overview"]),
                     tuple(RepoPost(r["ref"], r["subtitle"], claim(r["what"]), claim(r["why_now"]),
                                    claim(r["use_cases"]), idea(r["image"])) for r in d["repos"]),
                     idea(d["cover"]), tuple((c, a) for c, a in d["misreadings"]), d["summary"], d["next"],
                     tuple(d["tags"]))


def rerender(bi: BlogInput, *, work_dir: Path, published: Sequence[tuple[int, str, str]],
             log: Callable[[str], None] = print) -> dict[str, Any]:
    """저장한 초안으로 다시 그린다 — LLM 호출 0(그림 프롬프트·틀만 고쳤을 때). 이미지는 meta.json 그대로."""
    out = work_dir / bi.week / "blog"
    stats: dict[str, Any] = {"written": False, "stopped": None, "error": None, "excluded": 0}
    if not (out / "draft.json").exists():
        stats["error"] = f"저장한 초안이 없다: {out / 'draft.json'}"
        return stats
    meta = io.read_json(out / "meta.json") if (out / "meta.json").exists() else {}
    if "files" not in meta:     # 예전 meta.json — 받아 둔 그림을 img/ 에서 찾는다
        meta["files"] = {name: f"img/{hit[0].name}" for name in meta.get("images") or {}
                         if (hit := sorted((out / "img").glob(f"{name.replace('/', '__')}.*")))}
    return _write(out, bi, load_draft(out / "draft.json"), meta, stats, published=published, log=log)


def dry_run(writer: BlogWriter, bi: BlogInput) -> dict[str, Any]:
    """호출 0 — 실제로 보낼 요청 하나로 입력 토큰과 비용 범위를 낸다. 형식 오류로 다시 물으면 최대 2배."""
    req = writer.request(bi)
    typ = request_tokens(req.system, req.user, schema=True, typical=True)
    cons = request_tokens(req.system, req.user, schema=True)
    lo = cost(MODEL, Usage(typ, TYPICAL_OUTPUT))
    hi = cost(MODEL, Usage(cons, writer.max_tokens))
    return {"llm_calls": 1, "retry_max": 1, "episode": bi.episode, "top": [r.full_name for r in bi.repos],
            "sources": len(bi.sources), "input_tokens": [typ, cons],
            "total_usd": [round(lo, 4), round(hi, 4)], "total_usd_with_retry_max": round(2 * hi, 4),
            "assumptions": {"model": MODEL, "effort": writer.effort,
                            "output_tokens": [TYPICAL_OUTPUT, writer.max_tokens]},
            "fingerprint": writer.fingerprint}
