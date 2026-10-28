"""인용 게이트 (SPEC FR-7.1~7.3, PLAN 1-5) — 순수 함수. (본문, 근거 목록) → (통과 본문, 제외 로그).

카드·브리핑에 나온 URL 이 근거 목록(FR-5.6)이나 허용한 GitHub 저장소 URL 에 없으면 그 주장을 막는다.
LLM 이 지어낸 링크를 코드 단계에서 걸러 내기 위함이다. 막은 주장은 본문에서 빼되 지우지 않고
"출처 없음 — 제외됨"으로 로그에 남긴다(FR-7.3).

- 주장의 단위는 블록이다: 목록 항목(이어지는 줄 포함)·문단·표의 한 행·코드 블록·참조 정의.
- 렌더러가 링크로 만드는 모든 모양을 본다 — 인라인·이미지·자동 링크·맨 URL·www.·참조 링크·HTML 속성.
  HTML 엔티티(&#58;)와 백슬래시 이스케이프를 푼 형태도 함께 본다. 코드 안의 URL 도 막는다(보여 주기는 한다).
- 링크 대상이 웹 URL 이 아니면(javascript:·상대 경로·//호스트) 그것만으로 막는다.
- cited 섹션(카드 ③⑤⑥, 브리핑은 전체)의 목록 항목은 허용된 링크가 하나는 있어야 한다(FR-7.1).
"""

import html
import re
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass

from startrend.core.evidence import normalize_url

LABEL = "출처 없음 — 제외됨"
CARD_CITED = ("③", "⑤", "⑥")     # 카드에서 주장마다 출처가 있어야 하는 섹션 (FR-7.1)

_BARE = re.compile(r"(?i)(?:https?://|www\.)[^\s<>\"'`)\]]+")
_TRAILING = ".,;:!?*_~'\""
_LINK_TARGET = re.compile(r"\]\(\s*(<[^>\n]*>|[^\s)]*)")
_AUTOLINK = re.compile(r"<([a-zA-Z][a-zA-Z0-9+.-]{1,31}:[^\s<>]*)>")
_TAG = re.compile(r"<[a-zA-Z][^>]*>")
_ATTR = re.compile(r"(?i)\b(?:href|src|srcset|action|formaction|poster|background|cite|data|xlink:href)"
                   r"\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)")
_REF_DEF = re.compile(r"^\s{0,3}\[([^\]]+)\]:\s*(<[^>]*>|\S+)")
_REF_FULL = re.compile(r"\[([^\]]*)\]\[([^\]]*)\]")      # [글][label] · [label][]
_REF_SHORT = re.compile(r"\[([^\]]+)\](?![(\[:])")
_BACKSLASH = re.compile(r"\\([!-/:-@\[-`{-~])")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_ROW = re.compile(r"^\s*\|")
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")


@dataclass(frozen=True)
class Excluded:
    section: str
    line: int                    # 1부터 — 블록 첫 줄
    text: str
    urls: tuple[str, ...]        # 막힌 URL(쓰여 있던 그대로). 출처가 없어서 막혔으면 비어 있다
    reason: str                  # "unlisted_url" · "no_source"
    label: str = LABEL

    def as_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["urls"] = list(self.urls)
        return d


@dataclass(frozen=True)
class GateResult:
    body: str
    excluded: tuple[Excluded, ...]
    checked: int                 # 검사한 블록 수 (제목·빈 줄 제외)
    kept_links: int              # 통과한 블록의 서로 다른 허용 링크 수 합

    def log(self) -> list[dict[str, object]]:
        return [e.as_dict() for e in self.excluded]


@dataclass
class _Block:
    start: int                   # 0부터
    end: int                     # 포함하지 않음
    kind: str                    # heading · item · para · row · fence · refdef · blank
    section: str


def _ref_label(s: str) -> str:
    return " ".join(s.split()).casefold()


def _variants(text: str) -> set[str]:
    unescaped = html.unescape(text)
    return {text, unescaped, _BACKSLASH.sub(r"\1", text), _BACKSLASH.sub(r"\1", unescaped)}


def _urls_in(text: str) -> list[str]:
    """블록 안에서 링크가 될 수 있는 모든 대상. 웹 URL 이 아닌 링크 대상도 그대로 돌려준다(막는다)."""
    found: list[str] = []
    for v in sorted(_variants(text)):
        found += [m.group(0).rstrip(_TRAILING) for m in _BARE.finditer(v)]
        found += [m.group(1).strip("<>") for m in _LINK_TARGET.finditer(v)]
        found += [m.group(1) for m in _AUTOLINK.finditer(v)]
        for tag in _TAG.finditer(v):
            found += [m.group(1).strip("\"'") for m in _ATTR.finditer(tag.group(0))]
    out: list[str] = []
    for u in found:
        if u and u not in out:
            out.append(u)
    return out


def _blocks(lines: Sequence[str]) -> list[_Block]:
    blocks: list[_Block] = []
    section = ""
    fence: str | None = None
    for i, line in enumerate(lines):
        cur = blocks[-1] if blocks else None
        if fence is not None:
            assert cur is not None
            cur.end = i + 1
            m = _FENCE.match(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            continue
        if m := _FENCE.match(line):
            fence = m.group(1)
            blocks.append(_Block(i, i + 1, "fence", section))
        elif not line.strip():
            blocks.append(_Block(i, i + 1, "blank", section))
        elif h := _HEADING.match(line):
            section = h.group(2)
            blocks.append(_Block(i, i + 1, "heading", section))
        elif _REF_DEF.match(line):
            blocks.append(_Block(i, i + 1, "refdef", section))
        elif _ROW.match(line):
            blocks.append(_Block(i, i + 1, "row", section))
        elif _ITEM.match(line):
            blocks.append(_Block(i, i + 1, "item", section))
        elif cur is not None and cur.kind in ("item", "para") and cur.end == i:
            cur.end = i + 1                                   # 이어지는 줄
        else:
            blocks.append(_Block(i, i + 1, "para", section))
    return blocks


def allowed_set(evidence_urls: Iterable[str], repos: Iterable[str] = ()) -> set[str]:
    out = {k for u in evidence_urls if (k := normalize_url(u))}
    out |= {k for r in repos if (k := normalize_url(f"https://github.com/{r.strip('/')}"))}
    return out


def check(body: str, evidence_urls: Iterable[str], *, repos: Iterable[str] = (),
          cited: Sequence[str] = ()) -> GateResult:
    """evidence_urls: 근거 목록의 URL. repos: 링크를 허용할 GitHub 저장소(owner/name — 카드 대상·비교 대상).

    cited: 이 접두어로 시작하는 섹션의 목록 항목은 허용 링크가 있어야 한다. ("",) 이면 모든 섹션.
    """
    allowed = allowed_set(evidence_urls, repos)
    lines = body.split("\n")
    blocks = _blocks(lines)

    # 참조 정의는 문서 어디에 있든 전체에 적용된다 — 먼저 모은다
    refs: dict[str, str] = {}
    for b in blocks:
        if b.kind == "refdef" and (m := _REF_DEF.match(lines[b.start])):
            refs.setdefault(_ref_label(m.group(1)), m.group(2).strip("<>"))

    excluded: list[Excluded] = []
    drop: set[int] = set()
    checked = kept = 0
    for b in blocks:
        if b.kind == "blank":
            continue
        text = "\n".join(lines[b.start:b.end])
        urls = _urls_in(text)
        if b.kind != "refdef":
            labels = [m.group(2) or m.group(1) for m in _REF_FULL.finditer(text)] + \
                     [m.group(1) for m in _REF_SHORT.finditer(text)]
            urls += [refs[k] for k in map(_ref_label, labels) if k in refs and refs[k] not in urls]
        good = {k for u in urls if (k := normalize_url(u)) in allowed}
        bad = tuple(u for u in urls if normalize_url(u) not in allowed)
        if b.kind != "heading":
            checked += 1
        reason = None
        if bad:
            reason = "unlisted_url"
        elif b.kind == "item" and not good and any(b.section.startswith(p) for p in cited):
            reason = "no_source"
        if reason:
            excluded.append(Excluded(b.section, b.start + 1, text, bad, reason))
            drop.update(range(b.start, b.end))
        else:
            kept += len(good)
    passed = "\n".join(ln for i, ln in enumerate(lines) if i not in drop)
    return GateResult(passed, tuple(excluded), checked, kept)
