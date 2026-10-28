"""GeekNews 근거 (SPEC FR-5.5, 결정 44, 부록 C-2) — 공식 API 가 없어 `/past?day=` 날짜별 목록 HTML 을 읽는다.

- 근거 창(Target.since~until)의 날마다 1쪽부터, 다음 쪽이 있으면 max_pages 까지. 주 15~25회 정도다.
- 식별 가능한 User-Agent 와 요청 사이 간격(delay). robots 는 `/past` 를 허용하고,
  약관은 "과도한 부하"를 막는다.
- 한 주를 한 번 훑어 github.com/<owner>/<repo> 링크별로 나눠 두고, 대상마다 꺼낸다
  (대상마다 다시 부르지 않는다).
- 글 블록은 있는데 하나도 읽지 못하면 형식이 바뀐 것이다 — 0건으로 넘기지 않고 SourceError(FR-5.7 이 격리).
- 근거 URL 은 GeekNews 토론 페이지(topic?id=)다. 링크 대상은 대개 저장소 자신이다.
"""

import html
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlencode

from startrend.clients.evidence.base import SourceError, Target
from startrend.clients.transport import Transport, TransportError
from startrend.core import evidence as ev

BASE = "https://news.hada.io"
USER_AGENT = "startrend/0.0.1 (+https://github.com/daehyub71/github-ai-star-trend)"
DELAY_SECONDS = 2.0
MAX_PAGES = 3

_ROW = re.compile(r"<div class='topic_row'")
_ID = re.compile(r"data-topic-state-id='(\d+)'")
_LINK = re.compile(r"<a href='([^']+)'[^>]*class='topic-title-link'>\s*<h2[^>]*>(.*?)</h2>", re.S)
_DESC = re.compile(r"<div class='topicdesc'><a [^>]*>(.*?)</a>", re.S)
_POINTS = re.compile(r"<span id='tp\d+'>(\d+)</span>\s*points")
_TIME = re.compile(r'<time [^>]*datetime="([^"]+)"')
_COMMENTS = re.compile(r"data-topic-comment-count='(\d+)'")


@dataclass(frozen=True)
class Topic:
    topic_id: int
    link: str
    title: str
    desc: str
    points: int
    comments: int
    published_at: str | None


def _text(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def parse_past(page: str, day: str, page_no: int) -> tuple[list[Topic], bool]:
    """날짜별 목록 한 쪽 → (글 목록, 다음 쪽이 있는가)."""
    blocks = _ROW.split(page)[1:]
    topics: list[Topic] = []
    for b in blocks:
        tid, link = _ID.search(b), _LINK.search(b)
        if not tid or not link:
            continue
        desc, pts, tm, cm = _DESC.search(b), _POINTS.search(b), _TIME.search(b), _COMMENTS.search(b)
        topics.append(Topic(int(tid.group(1)), html.unescape(link.group(1)), _text(link.group(2)),
                            _text(desc.group(1)) if desc else "", int(pts.group(1)) if pts else 0,
                            int(cm.group(1)) if cm else 0, tm.group(1) if tm else None))
    if blocks and not topics:
        raise SourceError(f"GeekNews 목록 형식이 바뀌었다 ({day} {page_no}쪽: "
                          f"글 {len(blocks)}개를 읽지 못함)")
    nxt = f"past?day={day}&page={page_no + 1}"
    return topics, nxt in page or nxt.replace("&", "&amp;") in page


def _iso(t: str | None) -> str | None:
    if not t:
        return None
    try:
        d = datetime.fromisoformat(t)
    except ValueError:
        return None
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if d.tzinfo else None


class GeekNewsSource:
    def __init__(self, transport: Transport, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 sleep: Callable[[float], None] = time.sleep, delay: float = DELAY_SECONDS,
                 max_pages: int = MAX_PAGES, timeout: float = 30.0):
        self._t = transport
        self._clock = clock
        self._sleep = sleep
        self.delay = delay
        self.max_pages = max_pages
        self.timeout = timeout
        self.calls = 0
        self._weeks: dict[tuple[date, date], dict[str, list[ev.Evidence]]] = {}
        self._failed: dict[tuple[date, date], str] = {}

    @property
    def name(self) -> str:
        return "geeknews"

    def _get(self, day: str, page_no: int) -> str:
        if self.calls:
            self._sleep(self.delay)
        q = {"day": day} if page_no == 1 else {"day": day, "page": str(page_no)}
        self.calls += 1
        try:
            resp = self._t("GET", f"{BASE}/past?{urlencode(q)}",
                           {"User-Agent": USER_AGENT, "Accept": "text/html"}, self.timeout)
        except TransportError as e:
            raise SourceError(f"GeekNews 연결 실패: {e}") from e
        if resp.status != 200:
            raise SourceError(f"GeekNews {resp.status} ({day} {page_no}쪽)")
        return resp.body.decode("utf-8", errors="replace")

    def _scan(self, since: date, until: date) -> dict[str, list[ev.Evidence]]:
        now = self._clock()
        by_repo: dict[str, list[ev.Evidence]] = {}
        d = since
        while d <= until:
            day = d.isoformat()
            for page_no in range(1, self.max_pages + 1):
                topics, has_next = parse_past(self._get(day, page_no), day, page_no)
                for t in topics:
                    repo = ev.github_repo(t.link)
                    if repo is None:
                        continue
                    by_repo.setdefault(repo, []).append(ev.make(
                        url=f"{BASE}/topic?id={t.topic_id}", source="geeknews", kind="story", title=t.title,
                        text=f"{t.title}\n\n{t.desc}".strip(), fetched_at=now,
                        published_at=_iso(t.published_at),
                        extra={"points": t.points, "comments": t.comments, "linked_url": t.link}))
                if not has_next:
                    break
            d += timedelta(days=1)
        return by_repo

    def collect(self, target: Target) -> list[ev.Evidence]:
        key = (target.since, target.until)
        if key in self._failed:          # 실패한 주를 저장소마다 다시 훑지 않는다 — 부하를 주지 않기 위함
            raise SourceError(self._failed[key])
        if key not in self._weeks:
            try:
                self._weeks[key] = self._scan(*key)
            except SourceError as e:
                self._failed[key] = str(e)
                raise
        return list(self._weeks[key].get(target.full_name.lower(), []))
