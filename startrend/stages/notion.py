"""Notion 저장 (SPEC FR-15, 결정 34·38·59) — 비용 0(Notion API 만). 기본은 계획만(호출 0).

- `setup`: 사용자가 지정한 부모 페이지 아래 데이터베이스 3개(주간 · 저장소 카드 · 블로그 초안). 한 번만.
- `publish_week`: 그 주 AI 탭 저장소의 카드 페이지(저장소마다 한 장)
  → 주간 페이지(브리핑 + 4축 요약 + 카드 링크).
- `publish_blog`: 블로그 초안 페이지(주간 페이지와 연결).
- **상태가 "초안"이 아닌 페이지는 속성도 본문도 고치지 않는다**(NFR-16). 휴지통에 있거나 지워진 페이지도
  다시 만들지 않는다 — 사용자가 한 일이다. 로그에만 남긴다.
- 주·저장소 ↔ Notion 페이지 대응표는 `.work/notion/index.json`(결정 59 — 공개 저장소에 올리지 않는다).
  페이지 하나를 만들 때마다 저장해서, 중간에 멈춰도 같은 페이지를 두 번 만들지 않는다.
- 입력은 사이트 데이터(공개 `data/site/` + 비공개 사본 `.work/site-private/`) — 사이트와 같은 글이 간다.
"""

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from startrend.clients.notion import NotionClient, NotionError, status_name
from startrend.core import io

STATUS = "상태"
DRAFT = "초안"
STATUS_OPTIONS = (("초안", "gray", "To-do"), ("검토 중", "blue", "In progress"),
                  ("승인", "purple", "In progress"), ("게시됨", "green", "Complete"))
SITE_URL = "https://github-ai-star-trend.vercel.app"
AXES = (("gain", "지금 뜨는 저장소"), ("fresh", "새로 뜨는 저장소"), ("growth", "규모 대비 급성장"),
        ("total", "누적 스타 TOP"))
TOP = 5                     # 주간 페이지의 축별 요약 줄 수
TEXT_MAX = 2000             # rich_text 한 칸 (부록 C-3)
AI_NOTE = ("> **AI 작성** — 브리핑·카드는 AI(Claude)가 공개 자료로 쓴 요약이다. 사람이 검토하지 않았으며, "
           "주장마다 출처 링크를 붙였다. 숫자는 GitHub API 값을 코드가 채운다.")


class NotionStageError(Exception):
    pass


# --- 대응표 ---


def empty_index() -> dict[str, Any]:
    return {"parent_page_id": None, "databases": {}, "weeks": {}, "cards": {}, "blog": {}}


def load_index(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_index()
    return {**empty_index(), **io.read_json(path)}


def save_index(path: Path, idx: Mapping[str, Any]) -> None:
    io.write_json(path, dict(idx))


# --- 데이터베이스 ---


def _status() -> dict[str, Any]:
    return {"type": "status", "status": {"options": [{"name": n, "color": c, "group": g}
                                                     for n, c, g in STATUS_OPTIONS]}}


def _select(names: Sequence[str]) -> dict[str, Any]:
    return {"type": "select", "select": {"options": [{"name": n[:100]} for n in dict.fromkeys(names)]}}


def schemas(names: Mapping[str, str], types: Sequence[str]) -> dict[str, tuple[str, dict[str, Any]]]:
    """키 → (DB 제목, 속성). 블로그의 relation 대상은 만들 때 채운다."""
    num = {"type": "number", "number": {"format": "number"}}
    return {
        "weekly": ("주간", {"주": {"type": "title", "title": {}}, "주 시작": {"type": "date", "date": {}},
                          STATUS: _status(), "헤드라인": {"type": "rich_text", "rich_text": {}},
                          "랭킹 진입 수": num, "사이트": {"type": "url", "url": {}}}),
        "cards": ("저장소 카드", {"저장소": {"type": "title", "title": {}},
                             "카테고리": _select(list(names.values())), "유형": _select(types),
                             "처음 등장 주": {"type": "date", "date": {}}, "누적 스타": num,
                             "지난 주 증가": num, "카드 기준일": {"type": "date", "date": {}},
                             "GitHub": {"type": "url", "url": {}}, STATUS: _status()}),
        "blog": ("블로그 초안", {"제목": {"type": "title", "title": {}}, STATUS: _status(),
                            "네이버 글 주소": {"type": "url", "url": {}},
                            "게시일": {"type": "date", "date": {}}}),
    }


def setup(client: NotionClient, parent_page_id: str, idx: dict[str, Any], *, names: Mapping[str, str],
          types: Sequence[str]) -> dict[str, Any]:
    """FR-15.5 — 한 번만. 이미 만들었으면 멈춘다(같은 DB 를 둘 만들지 않게)."""
    if idx.get("databases"):
        raise NotionStageError("데이터베이스를 이미 만들었다 — 대응표(.work/notion/index.json)를 확인한다")
    idx["parent_page_id"] = parent_page_id
    for key, (title, props) in schemas(names, types).items():
        if key == "blog":
            weekly_ds = idx["databases"]["weekly"]["data_source_id"]
            props = {**props, "주": {"type": "relation",
                                    "relation": {"data_source_id": weekly_ds, "single_property": {}}}}
        db = client.create_database(parent_page_id, title, props)
        idx["databases"][key] = {"id": db.id, "data_source_id": db.data_source_id, "url": db.url}
    return idx


# --- 입력 ---


@dataclass(frozen=True)
class CardDoc:
    repo_id: int
    full_name: str
    slug: str
    markdown: str
    entry: Mapping[str, Any]
    first_week: str
    as_of: str


@dataclass(frozen=True)
class WeekDoc:
    week: str
    until: str
    names: Mapping[str, str]
    types: Sequence[str]
    axes: Mapping[str, Any]
    briefing: str | None
    headline: str
    ai_count: int
    cards: Sequence[CardDoc] = field(default_factory=tuple)


def _ai(axes: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    out: list[Mapping[str, Any]] = []
    for key, _ in AXES:
        out += (axes.get(key) or {}).get("ai") or []
    return out


def _lf(text: str) -> str:
    """줄바꿈을 LF 로 — 윈도우에서 쓴 파일도 같은 규칙으로 읽는다."""
    return "\n".join(text.splitlines()) + ("\n" if text.endswith(("\n", "\r")) else "")


def _front(md: str) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---\n", md, re.S)
    return dict(ln.split(": ", 1) for ln in m.group(1).splitlines() if ": " in ln) if m else {}


def body_of(md: str) -> str:
    """앞머리(---)와 맨 앞 제목(# …)을 뺀 본문 — 제목은 Notion 페이지 제목이 맡는다."""
    md = re.sub(r"^---\n.*?\n---\n", "", md, count=1, flags=re.S).lstrip("\n")
    return re.sub(r"^# [^\n]*\n+", "", md, count=1)


def _headline(briefing: str | None) -> str:
    for para in body_of(briefing or "").split("\n\n"):
        p = para.strip()
        if p and not p.startswith(("#", "|", "-", ">")):
            return " ".join(p.split())
    return ""


def load_week(site_dir: Path, private_dir: Path, week: str) -> WeekDoc:
    wfile = site_dir / "weeks" / f"{week}.json"
    if not wfile.exists():
        raise FileNotFoundError(f"사이트 데이터가 없다 — export 를 먼저: {wfile}")
    index = io.read_json(site_dir / "index.json")
    names = {c["id"]: c["name"] for c in index.get("categories", [])}
    data = io.read_json(wfile)
    first: dict[int, str] = {}
    for p in sorted((site_dir / "weeks").glob("*.json")):
        if p.stem <= week:
            for e in _ai(io.read_json(p).get("axes") or {}):
                first.setdefault(int(e["id"]), p.stem)
    ref_file = private_dir / "cards" / "index.json"
    refs = io.read_json(ref_file) if ref_file.exists() else []
    by_id = {int(r["repo_id"]): r for r in refs}
    cards: list[CardDoc] = []
    seen: set[int] = set()
    for e in _ai(data.get("axes") or {}):
        rid = int(e["id"])
        ref = by_id.get(rid)
        if rid in seen or ref is None:
            continue
        path = private_dir / "cards" / f"{ref['slug']}.md"
        if not path.exists():
            continue
        seen.add(rid)
        md = _lf(io.read_text(path))
        cards.append(CardDoc(rid, e["full_name"], ref["slug"], md, e, first.get(rid, week),
                             _front(md).get("as_of") or str(ref.get("as_of") or "")))
    bpath = private_dir / "briefings" / f"{week}.md"
    briefing = _lf(io.read_text(bpath)) if bpath.exists() else None
    axes = data.get("axes") or {}
    return WeekDoc(week, data.get("week_end", ""), names, list(index.get("types", [])), axes,
                   briefing, _headline(briefing), len({int(e["id"]) for e in _ai(axes)}), tuple(cards))


# --- 페이지 내용 ---


def _text(s: str) -> list[dict[str, Any]]:
    parts = [s[i:i + TEXT_MAX] for i in range(0, len(s), TEXT_MAX)][:100]
    return [{"type": "text", "text": {"content": p}} for p in parts]


def _fmt(n: Any) -> str:
    return f"{n:,}" if isinstance(n, int) else "—"


def _value(e: Mapping[str, Any], axis: str) -> str:
    if axis == "gain":
        return f"+{_fmt(e.get('gain'))}"
    if axis == "growth":
        g = e.get("growth")
        return f"+{g * 100:.1f}%" if isinstance(g, (int, float)) else "—"
    return _fmt(e.get("stars_end"))


def card_props(c: CardDoc, names: Mapping[str, str], *, new: bool) -> dict[str, Any]:
    cat = c.entry.get("category")
    props: dict[str, Any] = {
        "저장소": {"title": _text(c.full_name)},
        "카테고리": {"select": {"name": names.get(cat, cat)[:100]} if cat else None},
        "유형": {"select": {"name": str(c.entry["type"])[:100]} if c.entry.get("type") else None},
        "처음 등장 주": {"date": {"start": c.first_week}},
        "누적 스타": {"number": c.entry.get("stars_end")},
        "지난 주 증가": {"number": c.entry.get("gain")},
        "카드 기준일": {"date": {"start": c.as_of} if c.as_of else None},
        "GitHub": {"url": f"https://github.com/{c.full_name}"},
    }
    if new:
        props[STATUS] = {"status": {"name": DRAFT}}
    return props


def week_props(wd: WeekDoc, *, new: bool) -> dict[str, Any]:
    props: dict[str, Any] = {
        "주": {"title": _text(f"{wd.week} ~ {wd.until}")}, "주 시작": {"date": {"start": wd.week}},
        "헤드라인": {"rich_text": _text(wd.headline)}, "랭킹 진입 수": {"number": wd.ai_count},
        "사이트": {"url": f"{SITE_URL}/week/{wd.week}"}}
    if new:
        props[STATUS] = {"status": {"name": DRAFT}}
    return props


def week_markdown(wd: WeekDoc, card_urls: Mapping[int, str]) -> str:
    lines = [AI_NOTE, "", f"사이트에서 보기: [{wd.week} 주]({SITE_URL}/week/{wd.week})", ""]
    if wd.briefing:
        lines += [body_of(wd.briefing).rstrip(), ""]
    else:
        lines += ["이번 주 브리핑은 아직 없다.", ""]
    lines += [f"## 4축 랭킹 요약 — AI 탭 상위 {TOP}", ""]
    for key, title in AXES:
        rows = ((wd.axes.get(key) or {}).get("ai") or [])[:TOP]
        if not rows:
            continue
        lines += [f"### {title}", "", "| 순위 | 저장소 | 값 | 카드 |", "|---:|---|---:|---|"]
        for e in rows:
            url = card_urls.get(int(e["id"]))
            lines.append(f"| {e.get('rank', '')} | [{e['full_name']}](https://github.com/{e['full_name']}) | "
                         f"{_value(e, key)} | {f'[카드]({url})' if url else '—'} |")
        lines.append("")
    lines += [f"## 이번 주 카드 ({len(wd.cards)}장)", ""]
    for c in wd.cards:
        cat = c.entry.get("category")
        url = card_urls.get(c.repo_id)
        name = f"[{c.full_name}]({url})" if url else c.full_name
        lines.append(f"- {name} — {wd.names.get(cat, cat) if cat else 'AI'}")
    return "\n".join(lines).rstrip() + "\n"


def card_markdown(c: CardDoc) -> str:
    note = AI_NOTE.replace("브리핑·카드는", "이 카드는")
    return f"{note}\n\n{body_of(c.markdown).rstrip()}\n"


# --- 올리기 ---


def _upsert(client: NotionClient, section: dict[str, Any], key: str, ds_id: str, label: str,
            props: Callable[[bool], dict[str, Any]], markdown: str, stats: dict[str, int],
            log: Callable[[str], None], save: Callable[[], None]) -> str | None:
    """대응표에 있으면 초안일 때만 고치고, 없으면 만든다. 페이지 URL(쓸 수 없으면 None)."""
    known: dict[str, str] | None = section.get(key)
    if known is None:
        page = client.create_page(ds_id, props(True), markdown)
        section[key] = {"page_id": page.id, "url": page.url}
        save()
        stats["created"] += 1
        return page.url
    try:
        page = client.get_page(known["page_id"])
    except NotionError as e:
        if e.status != 404:
            raise
        stats["kept"] += 1
        log(f"  {label}: Notion 에 페이지가 없다(지워짐) — 다시 만들지 않는다")
        return known.get("url")
    if page.in_trash:
        stats["kept"] += 1
        log(f"  {label}: 휴지통에 있다 — 고치지 않는다")
        return known.get("url")
    state = status_name(page, STATUS)
    if state != DRAFT:
        stats["kept"] += 1
        log(f"  {label}: 상태가 '{state or '없음'}' — 고치지 않는다(NFR-16)")
        return known.get("url") or page.url
    client.update_properties(page.id, props(False))
    client.replace_markdown(page.id, markdown)
    stats["updated"] += 1
    return known.get("url") or page.url


def _db(idx: Mapping[str, Any], key: str) -> str:
    dbs = idx.get("databases") or {}
    if key not in dbs:
        raise NotionStageError("Notion 데이터베이스가 없다 — notion-setup 을 먼저 실행한다")
    return str(dbs[key]["data_source_id"])


def publish_week(client: NotionClient, idx: dict[str, Any], wd: WeekDoc, *,
                 save: Callable[[dict[str, Any]], None],
                 log: Callable[[str], None] = print) -> dict[str, int]:
    """카드 페이지 → 주간 페이지(카드 링크가 들어가야 해서 나중에)."""
    cards_ds, weekly_ds = _db(idx, "cards"), _db(idx, "weekly")
    stats = {"created": 0, "updated": 0, "kept": 0}
    urls: dict[int, str] = {}
    for c in wd.cards:
        def props(new: bool, c: CardDoc = c) -> dict[str, Any]:
            return card_props(c, wd.names, new=new)

        url = _upsert(client, idx["cards"], str(c.repo_id), cards_ds, c.full_name, props, card_markdown(c),
                      stats, log, lambda: save(idx))
        if url:
            urls[c.repo_id] = url
    _upsert(client, idx["weeks"], wd.week, weekly_ds, f"주간 {wd.week}", lambda new: week_props(wd, new=new),
            week_markdown(wd, urls), stats, log, lambda: save(idx))
    return stats


def publish_blog(client: NotionClient, idx: dict[str, Any], week: str, title: str, markdown: str, *,
                 save: Callable[[dict[str, Any]], None],
                 log: Callable[[str], None] = print) -> dict[str, int]:
    """블로그 초안 페이지(FR-16.3) — 주간 페이지가 있으면 연결한다."""
    blog_ds = _db(idx, "blog")
    weekly = (idx.get("weeks") or {}).get(week)

    def props(new: bool) -> dict[str, Any]:
        p: dict[str, Any] = {"제목": {"title": _text(title)}}
        if weekly:
            p["주"] = {"relation": [{"id": weekly["page_id"]}]}
        if new:
            p[STATUS] = {"status": {"name": DRAFT}}
        return p

    stats = {"created": 0, "updated": 0, "kept": 0}
    _upsert(client, idx["blog"], week, blog_ds, f"블로그 {week}", props, markdown, stats, log,
            lambda: save(idx))
    return stats


def plan(idx: Mapping[str, Any], wd: WeekDoc) -> dict[str, Any]:
    """호출 0 — 만들 페이지와 (초안이면) 고칠 페이지 수, 보낼 본문 크기(FR-15.6)."""
    known_cards = idx.get("cards") or {}
    create = sum(str(c.repo_id) not in known_cards for c in wd.cards)
    create += wd.week not in (idx.get("weeks") or {})
    pages = len(wd.cards) + 1
    chars = sum(len(card_markdown(c)) for c in wd.cards) + len(week_markdown(wd, {}))
    return {"week": wd.week, "set_up": bool(idx.get("databases")), "pages": pages, "create": create,
            "update_if_draft": pages - create, "cards": len(wd.cards), "markdown_chars": chars,
            "requests_max": create + 3 * (pages - create),
            "note": "상태가 '초안'이 아닌 페이지는 고치지 않는다(NFR-16). 요청은 초당 3회 미만"}


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
