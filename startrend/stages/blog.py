"""블로그 초안 (SPEC FR-16, 결정 36·37·39·59·60·61) — 과금 단계(주 1회 호출). dry-run 이 먼저다.

- 글 구성(결정 60, 2026-10-29 사용자): 지금 뜨는 저장소의 흐름 개괄 → TOP 10 순위 변동(결정 61 —
  지난주 대비 표 · 변동 해설 · 빠진 저장소) → **TOP 10 저장소마다 1. 무엇인가 · 2. 왜 지금 떴나 ·
  3. 활용 사례**(저장소 하나에 한글 500자 안팎) → 주의할 점 · 한 장 요약 · 다음 글 예고.
  대표 이미지는 저장소 소셜 미리보기(주인이 올린 것), 없으면 LLM 이 쓴 생성 프롬프트.
- 고정 틀은 코드가 채운다(견본 `docs/ref/blog-sample.md`, 결정 39) — 제목(이모지 + 시리즈 + 회차 + 핵심 3개),
  시리즈 소개, 정보 블록(⭐ 줄), TOP 순위 변동 표(지난주가 없으면 숫자 목록), 함께 보기(▶), 글 모음, 해시태그.
- LLM 은 정해진 JSON 으로 글만 쓴다. 출처는 번호(R1 · R1:E3)로만 가리킨다 — 주장마다 출처를 검사하지만
  글에는 적지 않는다(결정 64). 본문은 인용 게이트를 지난다. 형식 검사기(check_draft)가 막는다:
  글 안의 URL·마크다운 기호, 목록 밖 출처,
  출처 없는 주장, 입력에 없는 숫자(FR-6.5), 합쇼체가 아닌 문장(FR-16.6), TOP 순서, 분량. 걸리면 이유를 붙여
  한 번 다시 묻는다.
- 결과는 `.work/<주>/blog/`(결정 59 — 공개 저장소에 올리지 않는다). Notion 에는 `notion --run` 이 올린다.
- 저장소 빼기(결정 67): 안전 거절로 초안을 못 쓸 때 사람이 정한 저장소(`leave_out`)는 순위 표에만
  남긴다 — LLM 에는 그 카드와 브리핑의 언급 줄을 보내지 않고, 글에서 그 이름을 막는다.
  `meta.json` 에 남겨 다시 그릴 때 따른다.
- 내용 소제목마다 그림 하나(결정 65·68): 대표 · 이번 주 흐름 · TOP 순위 · 저장소마다 · 주의할 점 · 한 장 요약.
- 지난 회와 같은 내용 빼기(결정 69): 연재 소개 3문단은 1회에만. 지난주 글에도 나온 저장소는 지난 회 세 부분을
  LLM 에 함께 보내 새 사실만 쓰게 하고, 지난 회 글과 그대로 겹치는 구간을 형식 검사기가 막는다.
"""

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from startrend import gate
from startrend.budget import BudgetExceeded
from startrend.clients.llm import LLMClient, LLMRequest, Usage, cost, request_tokens
from startrend.core import cards, io, untrusted, weekfile

PROMPT_FILE = Path(__file__).resolve().parents[1] / "prompts" / "blog.md"
MODEL = "claude-opus-5-5"
EFFORT = "medium"
MAX_TOKENS = 32_000          # 사고 + JSON — 16,000 은 실측에서 모자랐다(MEASURE §27). 스트리밍으로 받는다
TYPICAL_OUTPUT = 8_000       # dry-run 하한 가정 — 첫 실행으로 실측

SERIES = "깃허브 AI 트렌드 주간 동향"        # 2026-10-26 사용자 결정 (FR-16.8)
SERIES_START = date(2026, 10, 18)           # 1회 주
EMOJI = "🤖"
REPO_URL = "https://github.com/daehyub71/github-ai-star-trend"
SITE_URL = "https://github-ai-star-trend.vercel.app"   # 함께 보기에만 — 공개·검색 비노출(결정 56)
CHANNEL = ("백발개발자의 바이브코딩", "https://www.youtube.com/@50VibeLog")
SERIES_TAGS = ("#깃허브AI트렌드", "#GitHub트렌드", "#AI트렌드", "#오픈소스", "#AI코딩")
CHANNEL_TAGS = ("#백발개발자", "#바이브코딩", "#오십로그", "#50Log", "#오십바이브로그", "#50바이브로그",
                "#50VibeLog")                # 견본 끝줄의 고정 채널 태그 (FR-16.8)
TOP_N = 10
CARD_SECTIONS = ("① 3줄 요약", "③ 왜 지금 떴나", "④ 무엇인가", "⑥ 활용사례")
PARTS = (("what", "무엇인가"), ("why_now", "왜 지금 떴나"), ("use_cases", "활용 사례"))
REPO_CHARS = (350, 750)      # 저장소 하나의 세 부분 합 — 사용자 "한글 500자 정도"
REPEAT_CHARS = (200, 750)    # 지난 회에 소개한 저장소 — 새 사실만 쓰면 짧아질 수 있다(결정 69, 처음 정한 값)
REPEAT_SPAN = 30             # 지난 회 글과 이만큼 그대로 겹치면 되풀이(결정 69)
#                              10-25 실측: 되풀이한 글 17~64자 · 대조군(다른 저장소끼리) 최대 15자
SMALL = {str(n) for n in range(0, 11)}       # 셈말로 쓰는 작은 수는 허용
SCENE_MIN = 400              # 그림 장면 프롬프트 최소 글자 수 — 구도·요소·라벨 자리까지 쓰게(결정 60)
LABELS = (2, 6)              # 그림에 나중에 얹을 한글 라벨 수
LABEL_MAX = 12
MOVER_PARAS = (2, 3)         # 순위 변동 해설 문단 수(결정 61)
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
GEN_DIR = "gen"                              # 사용자가 만든 그림 `gen/<번호>.<확장자>`(결정 62)
GEN_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")


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
    mark: str = ""                   # 지난주 대비 변동 표시(결정 61) — 지난주 데이터가 없으면 ""
    told: tuple[str, ...] = ()       # 지난 회 글의 세 부분(결정 69) — 지난주 글에 없었으면 ()


@dataclass(frozen=True)
class LeftOut:
    """사람이 글에서 빼기로 한 저장소(결정 67) — 순위 표에만 남고 설명·그림은 없다."""
    rank: int
    full_name: str
    mark: str = ""


LEFT_OUT_LINE = "이번 글에서는 이 저장소를 다루지 않습니다. 순위와 숫자는 위 표에 있습니다."
LEFT_OUT_IMAGE = "그림 없음 — 이번 글에서 다루지 않음"


@dataclass(frozen=True)
class Move:
    """TOP 표의 한 줄(결정 61)."""
    rank: int
    full_name: str
    gain: int | None
    prev_rank: int | None
    mark: str                        # ▲ n · ▼ n · – · 새로 진입 (사이트와 같다)
    was: str                         # 지난주 칸 — "5위 · +14,990" · "10월 17일 생성" · "15위 밖 · +2,028"
    new: bool                        # 지난주 시작 뒤에 생긴 저장소
    change: str                      # 증가 변화 — "-70%" · "8.5배" · ""(비교할 수 없음)


@dataclass(frozen=True)
class Dropped:
    """지난주 TOP 에 있다가 빠진 저장소."""
    ref: str                         # 출처 번호 D1, D2 …
    prev_rank: int
    full_name: str
    prev_gain: int | None
    gain: int | None                 # 이번 주 증가 — 모르면 None
    rank: int | None                 # 이번 주 AI 탭 순위 — 탭 밖이면 None
    change: str


@dataclass(frozen=True)
class Changes:
    prev_week: str
    top: int                         # 비교하는 TOP 크기
    kept: int                        # 지난주 TOP 중 남은 곳
    entered: int                     # 새로 들어온 곳
    cutoff: tuple[int | None, int | None]                 # TOP 마지막 순위의 증가 (지난주, 이번 주)
    moves: tuple[Move, ...]                               # 글에 쓰는 TOP 순서 그대로
    dropped: tuple[Dropped, ...]


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
    changes: Changes | None = None                        # 지난주 대비(결정 61) — 지난주 데이터가 없으면 None
    left_out: tuple[LeftOut, ...] = ()                    # 순위 표에만 남기는 저장소(결정 67)


def top_size(bi: BlogInput) -> int:
    """글이 다루는 TOP 크기 — 뺀 저장소도 순위 표에는 있으므로 센다."""
    return len(bi.repos) + len(bi.left_out)


def mentions(text: str, full_name: str) -> bool:
    """글에 그 저장소가 나오나 — 전체 이름, 또는 4자 이상인 저장소 이름(대소문자 무시).

    앞뒤가 영문·숫자·`_`·`-` 가 아니면 낱말로 본다 — 한글 조사가 붙어도("gpu-unlock은") 잡는다.
    """
    part = full_name.split("/")[-1]
    names = [full_name] + ([part] if len(part) >= 4 else [])
    return any(re.search(rf"(?<![A-Za-z0-9_-]){re.escape(n)}(?![A-Za-z0-9_-])", text, re.I) for n in names)


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


def move_mark(prev_rank: int | None, rank: int) -> str:
    """사이트(web/lib/rankings.ts)와 같은 변동 표시."""
    if prev_rank is None:
        return "새로 진입"
    d = prev_rank - rank
    return f"▲ {d}" if d > 0 else f"▼ {-d}" if d < 0 else "–"


def gain_change(now: Any, prev: Any) -> str:
    """증가 변화 — 2배 이상은 "8.5배", 그 밖은 "-70%". 비교할 수 없으면 ""."""
    if not isinstance(now, int) or not isinstance(prev, int) or prev <= 0:
        return ""
    r = now / prev
    return f"{r:.1f}배" if r >= 2 else f"{round((r - 1) * 100):+d}%"


def _plus(n: Any) -> str:
    return f"+{n:,}" if isinstance(n, int) else "—"


def _gain_ai(data: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list(((data.get("axes") or {}).get("gain") or {}).get("ai") or [])


def _week_gains(data_dir: Path | None, start: date) -> dict[int, int]:
    """주간 스타 파일의 증가 — AI 탭 밖 저장소의 지난주 증가를 여기서 찾는다. 없으면 빈 dict."""
    p = weekfile.week_path(data_dir, start) if data_dir is not None else None
    return {rid: r.gain for rid, r in weekfile.read(p).items()} if p is not None and p.exists() else {}


def _move(e: Mapping[str, Any], prev_by_id: Mapping[int, Mapping[str, Any]], old_gain: Mapping[int, int],
          size: int, prev_start: date) -> Move:
    rid, rank, now, pr = int(e["id"]), int(e.get("rank") or 0), e.get("gain"), e.get("prev_rank")
    created = date.fromisoformat(e["created"]) if e.get("created") else None
    if pr is not None:
        pg = (prev_by_id.get(rid) or {}).get("gain", old_gain.get(rid))
        return Move(rank, e["full_name"], now, pr, move_mark(pr, rank), f"{pr}위 · {_plus(pg)}", False,
                    gain_change(now, pg))
    if created is not None and created >= prev_start:
        return Move(rank, e["full_name"], now, None, move_mark(None, rank),
                    f"{created.month}월 {created.day}일 생성", True, "")
    pg = old_gain.get(rid)
    was = f"{size}위 밖" + (f" · {_plus(pg)}" if pg is not None else "")
    return Move(rank, e["full_name"], now, None, move_mark(None, rank), was, False, gain_change(now, pg))


def _changes(week: str, gain: list[Mapping[str, Any]], top: list[Mapping[str, Any]],
             prev: list[Mapping[str, Any]], data_dir: Path | None,
             sources: dict[str, tuple[str, str]]) -> Changes:
    """지난주 AI 탭과 비교(결정 61).

    남은 곳·새로 들어온 곳·빠진 곳은 카드 유무와 상관없이 AI 탭 순위로 센다.
    """
    start = date.fromisoformat(week)
    prev_start = start - timedelta(days=7)
    n = TOP_N

    def within(rows: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        return [e for e in rows if 1 <= int(e.get("rank") or 0) <= n]

    def gain_at(rows: list[Mapping[str, Any]]) -> int | None:
        return next((e.get("gain") for e in rows if int(e.get("rank") or 0) == n), None)

    prev_by_id = {int(e["id"]): e for e in prev}
    now_by_id = {int(e["id"]): e for e in gain}
    old_gain, new_gain = _week_gains(data_dir, prev_start), _week_gains(data_dir, start)
    prev_ids = {int(e["id"]) for e in within(prev)}
    now_ids = {int(e["id"]) for e in within(gain)}
    dropped: list[Dropped] = []
    for e in sorted(within(prev), key=lambda x: int(x["rank"])):
        rid, name = int(e["id"]), e["full_name"]
        if rid in now_ids:
            continue
        ref = f"D{len(dropped) + 1}"
        sources[ref] = (name, f"https://github.com/{name}")
        cur = now_by_id.get(rid)
        g = cur.get("gain") if cur else new_gain.get(rid)
        dropped.append(Dropped(ref, int(e["rank"]), name, e.get("gain"), g,
                               int(cur["rank"]) if cur else None, gain_change(g, e.get("gain"))))
    moves = tuple(_move(e, prev_by_id, old_gain, len(prev), prev_start) for e in top)
    return Changes(prev_start.isoformat(), n, len(prev_ids & now_ids), len(now_ids - prev_ids),
                   (gain_at(prev), gain_at(gain)), moves, tuple(dropped))


def load_input(site_dir: Path, private_dir: Path, week: str, *, data_dir: Path | None = None,
               leave_out: Sequence[str] = (), told: Mapping[str, Sequence[str]] | None = None) -> BlogInput:
    """data_dir: 주간 스타 파일(`stars/`)이 있는 곳 — AI 탭 밖 저장소의 지난주 증가를 찾는다(없어도 된다).

    leave_out: 순위 표에만 남길 저장소(결정 67) — TOP 안에 없으면 ValueError.
    told: 지난 회 글의 세 부분 {저장소: (무엇인가, 왜 지금 떴나, 활용 사례)}(결정 69, `previous_told`).
    """
    told = told or {}
    wfile = site_dir / "weeks" / f"{week}.json"
    if not wfile.exists():
        raise FileNotFoundError(f"사이트 데이터가 없다 — export 를 먼저: {wfile}")
    names = {c["id"]: c["name"] for c in io.read_json(site_dir / "index.json").get("categories", [])}
    data = io.read_json(wfile)
    gain = _gain_ai(data)
    pfile = site_dir / "weeks" / f"{(date.fromisoformat(week) - timedelta(days=7)).isoformat()}.json"
    prev = _gain_ai(io.read_json(pfile)) if pfile.exists() else []
    ref_file = private_dir / "cards" / "index.json"
    slugs = {int(r["repo_id"]): r["slug"] for r in (io.read_json(ref_file) if ref_file.exists() else [])}
    sources: dict[str, tuple[str, str]] = {}
    repos: list[BlogRepo] = []
    left: list[LeftOut] = []
    top: list[Mapping[str, Any]] = []
    for e in gain:
        if len(repos) + len(left) >= TOP_N:
            break
        rid, name, rank = int(e["id"]), e["full_name"], int(e.get("rank") or 0)
        if name in leave_out:          # 결정 67 — 순위 표에만, LLM 에는 보내지 않는다
            left.append(LeftOut(rank, name, move_mark(e.get("prev_rank"), rank) if prev else ""))
            top.append(e)
            continue
        p = private_dir / "cards" / f"{slugs[rid]}.md" if rid in slugs else None
        if p is None or not p.exists():
            continue
        ref = f"R{len(repos) + 1}"
        sources[ref] = (name, f"https://github.com/{name}")
        card = _convert_card(_lf(io.read_text(p)), ref, name, sources)
        repos.append(BlogRepo(ref, rank, rid, name, _cat(e, names), (_fact(e, names),), card,
                              move_mark(e.get("prev_rank"), rank) if prev else "", tuple(told.get(name, ()))))
        top.append(e)
    missing = sorted(set(leave_out) - {x.full_name for x in left})
    if missing:
        raise ValueError(f"AI 탭 TOP {TOP_N} 에 없는 저장소는 뺄 수 없다: {', '.join(missing)}")
    changes = _changes(week, gain, top, prev, data_dir, sources) if prev else None
    bpath = private_dir / "briefings" / f"{week}.md"
    briefing = _BARE.sub("", _LINK.sub(r"\1", _body(io.read_text(bpath)))).strip() if bpath.exists() else ""
    if left:                           # 뺀 저장소를 언급한 브리핑 줄도 보내지 않는다
        briefing = "\n".join(ln for ln in briefing.split("\n")
                             if not any(mentions(ln, x.full_name) for x in left))
    return BlogInput(week, data.get("week_end", ""), episode(week), names, briefing, tuple(top), tuple(repos),
                     sources, changes, tuple(left))


def _kdate(d: str, *, year: bool) -> str:
    x = date.fromisoformat(d)
    return f"{f'{x.year}년 ' if year else ''}{x.month}월 {x.day}일({WEEKDAY[x.weekday()]})"


def _change_facts(ch: Changes) -> list[str]:
    out = ["", f"rank changes vs last week ({ch.prev_week} week, AI tab, computed by code):",
           f"지난주 TOP {ch.top} 중 남은 곳 {ch.kept} · 새로 들어온 곳 {ch.entered}"]
    if all(isinstance(g, int) for g in ch.cutoff):
        out.append(f"{ch.top}위 문턱 지난주 {_plus(ch.cutoff[0])} → 이번 주 {_plus(ch.cutoff[1])}")
    for m in ch.moves:
        was = m.was if m.new else f"지난주 {m.was}"
        out.append(f"{m.rank}위 {m.mark} {m.full_name} — 이번 주 {_plus(m.gain)} · {was}"
                   + (f" · 증가 변화 {m.change}" if m.change else ""))
    if ch.dropped:
        refs = ", ".join(f"[{d.ref}]" for d in ch.dropped)
        out.append(f"dropped out of TOP {ch.top} (cite these as {refs}):")
        out += [f"[{d.ref}] 지난주 {d.prev_rank}위 {d.full_name} — 지난주 {_plus(d.prev_gain)} → "
                f"이번 주 {_plus(d.gain)}" + (f" · 증가 변화 {d.change}" if d.change else "")
                + (f" · 이번 주 {d.rank}위" if d.rank else "") for d in ch.dropped]
    return out


def _told(r: BlogRepo) -> str:
    """지난 회에 독자가 이미 읽은 세 부분(결정 69) — 같은 사실·사례·문장을 되풀이하지 않게."""
    parts = "\n".join(f"{label}: {text}" for (_, label), text in zip(PARTS, r.told, strict=False))
    return ("\nalready covered in last week's post — readers have read this. do not repeat its facts, "
            "examples or sentences; keep the three parts but write only what is new this week:\n" + parts)


def user_message(bi: BlogInput, *, with_told: bool = True) -> str:
    """with_told=False: 지난 회 글을 뺀 입력 — 형식 검사기의 숫자 허용 목록용(지난 회 숫자는 쓸 수 없다)."""
    facts = [f"series: {SERIES} · episode {bi.episode}",
             f"week: {_kdate(bi.week, year=True)} ~ {_kdate(bi.until, year=False)} (UTC)",
             f"TOP {len(bi.repos)} rising AI repositories (numbers computed by code):"]
    facts += [r.facts[0] for r in bi.repos]
    if bi.left_out:
        facts.append("left out of this post by the editor — do not mention or describe these anywhere: "
                     + ", ".join(f"{x.rank}위 {x.full_name}" for x in bi.left_out))
    if bi.changes:
        facts += _change_facts(bi.changes)
    if bi.briefing:
        facts += ["", "weekly briefing (already published on the site):", bi.briefing]
    items = [f"[{r.ref}] {r.full_name} · {r.category}\n" + "\n".join(r.facts) +
             f"\ncard (sources marked like [{r.ref}:E3]):\n{r.card}"
             + (_told(r) if with_told and r.told else "") for r in bi.repos]
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
    "overview_image": _IDEA,
    "movers": {"type": "array", "items": _CLAIM},
    "top_image": _IDEA,
    "repos": {"type": "array", "items": _obj({"ref": _STR, "subtitle": _STR, "what": _CLAIM,
                                              "why_now": _CLAIM, "use_cases": _CLAIM, "image": _IDEA})},
    "cover": _IDEA,
    "misreadings": {"type": "array", "items": _obj({"claim": _STR, "answer": _STR})},
    "summary": _STR,
    "next": _STR,
    "tags": _STRS,
    "caution_image": _IDEA,
    "summary_image": _IDEA,
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
    movers: tuple[Claim, ...] = ()   # 순위 변동 해설(결정 61) — 예전 초안에는 없다
    caution_image: ImageIdea | None = None   # 주의할 점 · 한 장 요약 그림(결정 65) — 예전 초안에는 없다
    summary_image: ImageIdea | None = None
    overview_image: ImageIdea | None = None  # 이번 주 흐름 · TOP 순위 그림(결정 68) — 예전 초안에는 없다
    top_image: ImageIdea | None = None


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
                     _strs(d.get("tags") or [], "tags"),
                     tuple(_claim(p, "movers") for p in d.get("movers") or []),
                     caution_image=_idea(d.get("caution_image"), "caution_image"),
                     summary_image=_idea(d.get("summary_image"), "summary_image"),
                     overview_image=_idea(d.get("overview_image"), "overview_image"),
                     top_image=_idea(d.get("top_image"), "top_image"))


_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_URLISH = re.compile(r"(?i)https?://|www\.|\.com/|\.io/")
_MARKDOWN = re.compile(r"\*\*|`|\]\(|^\s*#|^\s*[-*] |\[[^\]]*\]")
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]")


def _numbers(text: str) -> set[str]:
    return {t.replace(",", "") for t in _NUM.findall(text)}


def repeated(text: str, old: str) -> str:
    """지난 회 글과 그대로 겹치는 구간(REPEAT_SPAN 자 이상, 결정 69) — 없으면 "". 띄어쓰기 차이는 무시한다."""
    a, b = " ".join(text.split()), " ".join(old.split())
    for i in range(len(a) - REPEAT_SPAN + 1):
        if a[i:i + REPEAT_SPAN] in b:
            j = i + REPEAT_SPAN
            while j < len(a) and a[i:j + 1] in b:
                j += 1
            return a[i:j]
    return ""


def check_draft(dr: BlogDraft, bi: BlogInput) -> list[str]:
    """형식 검사기 — 빈 목록이면 통과. 메시지는 LLM 에게 다시 물을 때 그대로 붙인다."""
    errors: list[str] = []
    allowed = _numbers(user_message(bi, with_told=False)) | SMALL | {str(bi.episode)}
    src = {r.ref: r for r in bi.repos}
    claims: list[tuple[str, Claim]] = [(f"overview para {i + 1}", c) for i, c in enumerate(dr.overview)]
    claims += [(f"movers para {i + 1}", c) for i, c in enumerate(dr.movers)]
    if bi.changes and not MOVER_PARAS[0] <= len(dr.movers) <= MOVER_PARAS[1]:
        errors.append(f"movers — 지난주 대비 순위 변동 해설을 {MOVER_PARAS[0]}~{MOVER_PARAS[1]}문단으로 "
                      f"(got {len(dr.movers)})")
    want = [r.ref for r in bi.repos]
    got = [r.ref for r in dr.repos]
    if got != want:
        errors.append(f"repos 순서 — write exactly {want} in this order (got {got})")
    for r in dr.repos:
        claims += [(f"{r.ref} {label}", getattr(r, key)) for key, label in PARTS]
        n = sum(len(getattr(r, key).text) for key, _ in PARTS)
        told = src[r.ref].told if r.ref in src else ()
        lo, hi = REPEAT_CHARS if told else REPO_CHARS
        if not lo <= n <= hi:
            errors.append(f"{r.ref} 분량 — 세 부분 합 {n}자, 저장소 하나에 한글 500자 안팎({lo}~{hi}자)")
        old = " ".join(told)
        for key, label in PARTS if told else ():
            span = repeated(getattr(r, key).text, old)
            if span:
                errors.append(f"{r.ref} {label}: 지난 회 글과 같은 구간 '{span}' — "
                              "되풀이하지 말고 이번 주의 새 사실로 쓴다")
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
    ideas = [("cover", dr.cover)] + [(f"{r.ref} image", r.image) for r in dr.repos]
    extra = (("caution_image", dr.caution_image), ("summary_image", dr.summary_image),
             ("overview_image", dr.overview_image), ("top_image", dr.top_image))
    ideas += [(k, i) for k, i in extra if i]
    for where, idea in ideas:
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
        for x in bi.left_out:
            if mentions(t, x.full_name):
                errors.append(f"{where}: {x.full_name} 은 이번 글에서 빼기로 한 저장소 — 언급하지 않는다")
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


def _rank_line(e: Mapping[str, Any], names: Mapping[str, str]) -> str:
    name = e["full_name"]
    return (f"{e.get('rank')}위 {name} — 지난 주 +{_fmt(e.get('gain'))} 스타 · "
            f"누적 {_fmt(e.get('stars_end'))} · {_cat(e, names)}")


def title_of(bi: BlogInput, dr: BlogDraft) -> str:
    return f"{EMOJI} {SERIES} {bi.episode}회 {EMOJI} " + " · ".join(dr.title_points)


def _heading(r: BlogRepo, p: RepoPost) -> str:
    return f"{r.rank}위 {f'{r.mark} ' if r.mark else ''}{r.full_name} — {p.subtitle}"


def _change_block(bi: BlogInput, dr: BlogDraft, ch: Changes) -> list[str]:
    """TOP 순위 변동(결정 61) — 요약 줄 · 표 · 변동 해설 · 빠진 저장소."""
    out = [f"⭐ 지난주 TOP {ch.top} 중 남은 곳 : {ch.kept}곳 · 새로 들어온 곳 : {ch.entered}곳"]
    if all(isinstance(g, int) for g in ch.cutoff):
        out.append(f"⭐ {ch.top}위 문턱 : 지난주 {_plus(ch.cutoff[0])} → 이번 주 {_plus(ch.cutoff[1])}")
    rows = ["| 순위 | 변동 | 저장소 | 이번 주 | 지난주 |", "|---|---|---|---|---|"]
    rows += [f"| {m.rank}위 | {m.mark} | {m.full_name} | {_plus(m.gain)} | {m.was} |" for m in ch.moves]
    out.append("\n".join(rows))
    out += [c.text for c in dr.movers]
    if ch.dropped:
        out.append(f"TOP {ch.top} 에서 빠진 저장소 — 지난주 순위 · 지난주 증가 → 이번 주 증가")
        out += [f"지난주 {d.prev_rank}위 {d.full_name} — "
                f"{_plus(d.prev_gain)} → {_plus(d.gain)}" + (f" · 이번 주 {d.rank}위" if d.rank else "")
                for d in ch.dropped]
    return out


def _series_intro(n: int) -> list[str]:
    """머리말 — 연재를 시작한 이유(2026-10-30 사용자가 쓴 기획 의도를 다듬은 것).

    3문단은 1회에만, 2회부터는 세 문장(결정 69 — 지난 회와 같은 내용 빼기).
    """
    if n > 1:
        return [f"「{SERIES}」의 {n}번째 글입니다. GitHub 에서 스타를 많이 받은 AI 저장소를 매주 모아 "
                "어떤 흐름이 생기는지 숫자와 근거로 확인합니다. "
                "연재를 시작한 이유는 1회 글에 적어 두었습니다."]
    return [f"「{SERIES}」의 {n}번째 글입니다. 이 연재는 오픈소스의 최근 흐름을 파악하려고 시작한 작은 "
            "프로젝트입니다. 오픈소스의 본고장인 GitHub 에서 스타를 많이 받은 저장소를 매주 모아, "
            "어떤 흐름이 생기는지 숫자와 근거로 확인합니다.",
            "요즘 AI 관련 유튜브 영상을 보다 보면 하나의 흐름이 보입니다. 새로운 개념은 보통 X(옛 트위터)의 "
            "글로 먼저 알려지고, 그 개념을 구체적으로 구현한 결과물은 GitHub 에 공개됩니다. 그중 스타를 많이 "
            "받은 저장소가 AI 기술 트렌드를 이끄는 프로젝트로 보입니다.",
            "그래서 실무에 쓰기 좋은 개념과 구현 결과물(MCP, 라이브러리, 도구)을 꾸준히 모아 트렌드를 "
            "따라가고, 그중 업무에 필요한 것은 먼저 적용해 보려고 이 연재를 기획했습니다."]


def generated_images(out: Path) -> dict[int, str]:
    """사용자가 만든 그림(결정 62) — `gen/<번호>.<확장자>` → {번호: 상대 경로}.

    0 = 대표 그림, 그 밖은 순위(사진 배치 문서의 "생성 프롬프트 N").
    """
    d = out / GEN_DIR
    if not d.is_dir():
        return {}
    found: dict[int, str] = {}
    for f in sorted(d.iterdir()):
        if f.is_file() and re.fullmatch(r"[0-9]+", f.stem) and f.suffix.lower() in GEN_EXTS:
            found.setdefault(int(f.stem), f"{GEN_DIR}/{f.name}")
    return found


CAUTION_HEAD = "이번 주 숫자를 읽을 때 주의할 점"
SUMMARY_HEAD = "한 장 요약"


def extra_slots(bi: BlogInput) -> tuple[int, int, int, int]:
    """주의할 점 · 한 장 요약(결정 65) · 이번 주 흐름 · TOP 순위(결정 68) 그림 번호 — TOP 다음 번호.

    TOP 10 이면 11 · 12 · 13 · 14. 뺀 저장소도 센다. 결정 68 의 두 번호는 뒤에 붙인다 — 이미 만든 그림
    (`gen/11` · `gen/12`)의 번호를 바꾸지 않으려고.
    """
    n = max([r.rank for r in bi.repos] + [x.rank for x in bi.left_out], default=0)
    return n + 1, n + 2, n + 3, n + 4


def _overview_head(dr: BlogDraft) -> str:
    return f"이번 주 흐름 — {dr.overview_heading}"


def _top_head(bi: BlogInput) -> str:
    return f"TOP {top_size(bi)} — 지금 뜨는 AI 저장소" + (", 지난주와 비교" if bi.changes else "")


def _ranked(bi: BlogInput) -> list[BlogRepo | LeftOut]:
    """저장소 칸 순서 — 뺀 저장소(결정 67)는 제 순위 자리에 한 줄로 들어간다."""
    return sorted([*bi.repos, *bi.left_out], key=lambda r: r.rank)


def _left_head(x: LeftOut) -> str:
    return f"{x.rank}위 {f'{x.mark} ' if x.mark else ''}{x.full_name}"


def _extra(bi: BlogInput, dr: BlogDraft) -> list[tuple[int, str, ImageIdea]]:
    """(번호, 소제목, 그림) — 글 순서(이번 주 흐름 · TOP 순위 · 주의할 점 · 한 장 요약).

    예전 초안처럼 그림이 없는 자리는 뺀다.
    """
    caution, summary, overview, top = extra_slots(bi)
    pairs = ((overview, _overview_head(dr), dr.overview_image), (top, _top_head(bi), dr.top_image),
             (caution, CAUTION_HEAD, dr.caution_image), (summary, SUMMARY_HEAD, dr.summary_image))
    return [(no, head, idea) for no, head, idea in pairs if idea]


def _caption(text: str) -> str:
    return re.sub(r"[\[\]]", " ", text).strip()


def _slot(what: str, idea: ImageIdea) -> list[str]:
    """그림이 들어갈 자리 — 가르칠 것 · 얹을 라벨 한 줄 + 복사해 쓰는 프롬프트(코드 블록)."""
    return [f"> 🎨 {what} — {idea.teaches} · 얹을 라벨: {' · '.join(idea.labels)}",
            f"```text\n{idea.prompt()}\n```"]


def render(bi: BlogInput, dr: BlogDraft, *, published: Sequence[tuple[int, str, str]],
           images: Mapping[str, str], gen: Mapping[int, str] | None = None
           ) -> tuple[str, str, gate.GateResult]:
    """(제목, 본문 마크다운, 게이트 결과). 소제목은 ###(FR-16.5 ④ — R22 시험 B) · 링크는 넣지 않는다(결정 64).

    저장소마다 세 부분 이름(무엇인가 · 왜 지금 떴나 · 활용 사례)은 굵은 글씨 문단, 설명은 다음 문단 —
    제목 4(####)는 네이버에 붙이면 글자가 본문보다 작아졌다(결정 64). 문단 끝 출처 괄호도 없다 — 출처 번호는
    형식 검사기·draft.json 에만 남는다. 데이터 저장소·채널 주소는 글자 그대로.

    gen: 사용자가 만든 그림 {번호: 상대 경로}(결정 62) — 그 자리의 프롬프트 칸·소셜 미리보기 대신 들어간다.
    상대 경로는 인용 게이트가 막는 링크라, 게이트를 지난 뒤 코드가 넣는다(LLM 이 쓴 링크가 아니다).
    """
    n = bi.episode
    posts = {p.ref: p for p in dr.repos}
    pictures: dict[str, str] = {}

    def picture(slot: int, idea: ImageIdea, what: str) -> list[str]:
        if gen and slot in gen:
            key = f"§gen:{slot}§"
            pictures[key] = f"![{_caption(idea.teaches)}]({gen[slot]})"
            return [key]
        return _slot(what, idea)

    extra = {head: picture(no, idea, "그림 자리") for no, head, idea in _extra(bi, dr)}
    ov_head, top_head = _overview_head(dr), _top_head(bi)
    out: list[str] = [
        *picture(0, dr.cover, "대표 이미지 자리"), *_series_intro(n), dr.intro, f"***{SERIES} {n}회 정보***",
        f"⭐ 이 글의 내용 : 이번 주 흐름 한눈에 · {'지난주 대비 순위 변동 · ' if bi.changes else ''}"
        f"TOP {top_size(bi)} 저장소"
        "(무엇인가 · 왜 지금 떴나 · 활용 사례) · 숫자를 읽을 때 주의할 점 · 한 장 요약",
        f"⭐ 집계 기간 : {_kdate(bi.week, year=True)} ~ {_kdate(bi.until, year=False)}, UTC 기준",
        "⭐ 데이터 기준 : 스타 1,000개 이상 저장소 전체 스냅샷과 상위 후보의 일별 스타 · "
        "AI 여부와 카테고리는 Claude 가 판정 · 숫자는 GitHub API 값을 코드가 계산",
        "⭐ 쓰는 방식 : 숫자는 코드가, 글 초안은 AI(Claude)가 쓰고 사람이 검토합니다",
        f"⭐ 데이터 저장소 : {REPO_URL}",
        f"### {ov_head}", *extra.get(ov_head, [])]
    out += [c.text for c in dr.overview]
    out += [f"### {top_head}", *extra.get(top_head, [])]
    if bi.changes:
        out += _change_block(bi, dr, bi.changes)
    else:
        out += [_rank_line(e, bi.names) for e in bi.top]
    for r in _ranked(bi):
        if isinstance(r, LeftOut):     # 결정 67 — 설명·그림 자리 없이 한 줄
            out += [f"### {_left_head(r)}", LEFT_OUT_LINE]
            continue
        p = posts.get(r.ref)
        if p is None:
            continue
        out.append(f"### {_heading(r, p)}")
        if gen and r.rank in gen:
            out += picture(r.rank, p.image, "그림 자리")
        elif r.full_name in images:
            out += [f"![{r.full_name} 대표 이미지]({images[r.full_name]})",
                    f"이미지: {r.full_name} 저장소의 소셜 미리보기"]
        else:
            out += _slot("그림 자리", p.image)
        for i, (key, label) in enumerate(PARTS, 1):   # 부분 이름은 굵은 글씨, 본문과 같은 크기
            out += [f"**{i}. {label}**", getattr(p, key).text]
    out += [f"### {CAUTION_HEAD}", *extra.get(CAUTION_HEAD, [])]
    out += [f"{c} — {a}" for c, a in dr.misreadings]
    out += [f"### {SUMMARY_HEAD}", *extra.get(SUMMARY_HEAD, []), dr.summary, dr.next, "### 함께 보기",
            f"▶ 주간 트렌드 사이트 : {SITE_URL}", f"▶ 데이터 저장소(GitHub) : {REPO_URL}",
            f"▶ 채널 : {CHANNEL[0]} {CHANNEL[1]}", f"### {SERIES} 글 모음"]
    out += [f"▶ {k}회 {t} : {u}" for k, t, u in published if k != n]
    out.append(f"▶ {n}회 {' · '.join(dr.title_points)} (이 글)")
    tags = [*SERIES_TAGS, *(_tag(t) for t in dr.tags), *CHANNEL_TAGS]
    out.append(" ".join(t for t in dict.fromkeys(tags) if t))
    body = "\n\n".join(out) + "\n"
    urls = ([u for _, u in bi.sources.values()] + [REPO_URL, SITE_URL, CHANNEL[1]]
            + [u for _, _, u in published])
    res = gate.check(body, urls + list(images.values()), repos=[r.full_name for r in bi.repos])
    passed = res.body
    for key, line in pictures.items():
        passed = passed.replace(key, line)
    return title_of(bi, dr), passed, res


def images_doc(bi: BlogInput, dr: BlogDraft, *, images: Mapping[str, str], files: Mapping[str, str],
               gen: Mapping[int, str] | None = None) -> str:
    """사진 배치 문서(FR-16.7) — 소제목 → 이미지, 생성 프롬프트, 대표 이미지. gen: 만든 그림(결정 62)."""
    gen = gen or {}
    posts = {p.ref: p for p in dr.repos}
    cover = f"{gen[0]} (만든 그림)" if 0 in gen else "생성 프롬프트 0"
    rows = [f"| (머리말) | 대표 이미지 — {cover} |"]

    def block(head: str, idea: ImageIdea) -> list[str]:
        return [f"### {head}", "", f"- 가르칠 것: {idea.teaches}",
                f"- 얹을 라벨: {' · '.join(idea.labels)}", "", "```text", idea.prompt(), "```", ""]

    prompts = block("0. 대표 이미지(글 맨 위)" + (f" — 만든 그림: {gen[0]}" if 0 in gen else ""), dr.cover)
    alternatives: list[str] = []

    found = {head: (no, idea) for no, head, idea in _extra(bi, dr)}

    def extra(head: str) -> bool:
        """소제목 그림(결정 65·68) — 표 한 줄 + 프롬프트. 예전 초안처럼 그림이 없으면 False."""
        if head not in found:
            return False
        no, idea = found[head]
        if no in gen:
            where = f"{gen[no]} (만든 그림)"
            prompts.extend(block(f"{no}. {head} — 만든 그림: {gen[no]}", idea))
        else:
            where = f"생성 프롬프트 {no}"
            prompts.extend(block(f"{no}. {head}", idea))
        rows.append(f"| {head} | {where} |")
        return True

    if not extra(_overview_head(dr)):
        rows.append(f"| {_overview_head(dr)} | — |")
    extra(_top_head(bi))
    for r in _ranked(bi):
        if isinstance(r, LeftOut):
            rows.append(f"| {_left_head(r)} | {LEFT_OUT_IMAGE} |")
            continue
        p = posts.get(r.ref)
        if p is None:
            continue
        if r.rank in gen:
            where = f"{gen[r.rank]} (만든 그림)"
            prompts += block(f"{r.rank}. {r.full_name} — 만든 그림: {gen[r.rank]}", p.image)
        elif r.full_name in images:
            where = f"{files[r.full_name]} (저장소 소셜 미리보기)" if r.full_name in files \
                else f"{images[r.full_name]} (저장소 소셜 미리보기)"
            alternatives += block(f"(대안) {r.rank}. {r.full_name} — 소셜 미리보기 대신 교육용 그림을 쓸 때",
                                  p.image)
        else:
            where = f"생성 프롬프트 {r.rank}"
            prompts += block(f"{r.rank}. {r.full_name}", p.image)
        rows.append(f"| {_heading(r, p)} | {where} |")
    for head in (CAUTION_HEAD, SUMMARY_HEAD):
        extra(head)
    return "\n".join([
        f"# {title_of(bi, dr)} — 사진 배치 참고", "",
        "> 본문: `post.md` · 이미지: `img/`(저장소 소셜 미리보기를 받아 둔 것) · `gen/`(만든 그림 — "
        "파일 이름은 아래 생성 프롬프트 번호, 0 = 대표 그림). 없는 자리는 아래 생성 프롬프트로 만든다.",
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
        self.rejected: list[dict[str, Any]] = []      # 형식 검사에 걸린 답 — 과금된 출력을 버리지 않고 남긴다

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
                self.rejected.append({"problems": [error], "text": resp.text})
                continue
            problems = check_draft(dr, bi)
            if not problems:
                return dr
            error = "; ".join(problems[:15])
            self.rejected.append({"problems": problems, "text": resp.text})
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
        return _keep_rejected(out, bi, writer, stats, log)
    except BlogError as e:
        stats["error"] = str(e)
        log(f"  블로그 초안 실패 — {e}")
        return _keep_rejected(out, bi, writer, stats, log)
    io.write_json(out / "draft.json", asdict(dr))
    meta = {"week": bi.week, "episode": bi.episode, "generated": today.isoformat(),
            "fingerprint": writer.fingerprint, "top": [r.full_name for r in bi.repos],
            "left_out": [x.full_name for x in bi.left_out], "images": dict(images), "files": dict(files)}
    return _write(out, bi, dr, meta, stats, published=published, log=log)


def _keep_rejected(out: Path, bi: BlogInput, writer: BlogWriter, stats: dict[str, Any],
                   log: Callable[[str], None]) -> dict[str, Any]:
    """초안을 못 썼을 때 형식 검사에 걸린 답과 이유를 `rejected.json` 에 남긴다 — 무엇을 고칠지 보려고."""
    if writer.rejected:
        io.write_json(out / "rejected.json", {"week": bi.week, "fingerprint": writer.fingerprint,
                                              "answers": writer.rejected})
        stats["rejected"] = len(writer.rejected)
        for i, a in enumerate(writer.rejected, 1):
            log(f"  걸린 답 {i}: " + "; ".join(a["problems"][:5]))
    return stats


def saved_left_out(work_dir: Path, week: str) -> tuple[str, ...]:
    """저장한 초안이 뺀 저장소(결정 67) — `--from-draft` 가 같은 입력으로 다시 그리도록."""
    p = work_dir / week / "blog" / "meta.json"
    return tuple(io.read_json(p).get("left_out") or ()) if p.exists() else ()


def _write(out: Path, bi: BlogInput, dr: BlogDraft, meta: dict[str, Any], stats: dict[str, Any], *,
           published: Sequence[tuple[int, str, str]], log: Callable[[str], None]) -> dict[str, Any]:
    images, files = meta.get("images") or {}, meta.get("files") or {}
    gen = generated_images(out)               # 사용자가 만든 그림 — 매번 폴더에서 다시 찾는다(결정 62)
    title, body, res = render(bi, dr, published=published, images=images, gen=gen)
    io.write_text_atomic(out / "post.md", f"# {title}\n\n{body}")
    io.write_text_atomic(out / "images.md", images_doc(bi, dr, images=images, files=files, gen=gen))
    io.write_json(out / "gate.json", {"checked": res.checked, "kept_links": res.kept_links,
                                      "excluded": res.log()})
    io.write_json(out / "meta.json", {**meta, "chars": len(body),
                                      "generated": {str(k): v for k, v in gen.items()}})
    slots = {0} | {r.rank for r in bi.repos} | {no for no, _, _ in _extra(bi, dr)}
    filled = set(gen) | {r.rank for r in bi.repos if r.full_name in images}
    stats.update(written=True, excluded=len(res.excluded), file=str(out / "post.md"), title=title,
                 chars=len(body), images=len(images), generated=len(gen), prompts=len(slots - filled))
    log(f"  블로그 초안 — {len(body):,}자 · 게이트 제외 {len(res.excluded)}건 · "
        f"대표 이미지 {len(images)}개 · 만든 그림 {len(gen)}개")
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
                     tuple(d["tags"]), tuple(claim(c) for c in d.get("movers") or []),
                     caution_image=idea(d["caution_image"]) if d.get("caution_image") else None,
                     summary_image=idea(d["summary_image"]) if d.get("summary_image") else None,
                     overview_image=idea(d["overview_image"]) if d.get("overview_image") else None,
                     top_image=idea(d["top_image"]) if d.get("top_image") else None)


def previous_told(work_dir: Path, week: str) -> dict[str, tuple[str, ...]]:
    """지난주 글이 저장소마다 쓴 세 부분(결정 69) — {저장소: (무엇인가, 왜 지금 떴나, 활용 사례)}.

    지난주 `draft.json` · `meta.json`(R 번호 → 저장소)이 없으면 빈 dict — 보통처럼 쓴다.
    """
    prev = (date.fromisoformat(week) - timedelta(days=7)).isoformat()
    out = work_dir / prev / "blog"
    if not (out / "draft.json").exists() or not (out / "meta.json").exists():
        return {}
    top = io.read_json(out / "meta.json").get("top") or []
    told: dict[str, tuple[str, ...]] = {}
    for r in io.read_json(out / "draft.json").get("repos") or []:
        i = int(r["ref"][1:]) - 1
        if 0 <= i < len(top):
            told[top[i]] = tuple(r[key]["text"] for key, _ in PARTS)
    return told


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
            "left_out": [x.full_name for x in bi.left_out], "told": [r.full_name for r in bi.repos if r.told],
            "sources": len(bi.sources),
            "input_tokens": [typ, cons],
            "total_usd": [round(lo, 4), round(hi, 4)], "total_usd_with_retry_max": round(2 * hi, 4),
            "assumptions": {"model": MODEL, "effort": writer.effort,
                            "output_tokens": [TYPICAL_OUTPUT, writer.max_tokens]},
            "fingerprint": writer.fingerprint}
