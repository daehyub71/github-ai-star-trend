"""근거 문서 (SPEC FR-5.6·5.8). 모은 문서마다 URL·가져온 시각·콘텐츠 해시를 남긴다.

이 목록이 인용 게이트(FR-7)의 기준이다 — 카드·브리핑에 나온 URL 은 여기 있는 것(또는 GitHub 저장소 URL)만
통과한다. 그래서 URL 비교는 정규화한 형태로 한다(대소문자·www·끝 슬래시·추적 파라미터·조각).
원문(text)은 정본에 넣지 않는다. 기록(record)에는 짧은 인용(excerpt)과 해시만 남긴다(FR-5.8).
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

from startrend.core import hashing

EXCERPT_CHARS = 300
_DROP_PARAMS = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid")
_PATH_SAFE = "/:@!$&'()*+,;=-._~"
_CASELESS_PATH_HOSTS = ("github.com",)   # 소유자·저장소 이름은 대소문자를 가리지 않는다


def normalize_url(raw: str) -> str | None:
    """웹 링크(http·https, 또는 www. 로 시작)를 비교용 형태로. 그 밖(javascript:·상대 경로 등)은 None."""
    s = raw.strip()
    if s.lower().startswith("www."):
        s = "https://" + s
    try:
        parts = urlsplit(s)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    if parts.username is not None:          # 사용자 정보는 지우지 않는다 — 다른 호스트로 보이게 하는 속임수
        netloc = f"{parts.username}@{netloc}"
    path = quote(unquote(parts.path), safe=_PATH_SAFE).rstrip("/")
    if host in _CASELESS_PATH_HOSTS:
        segs = path.split("/")
        path = "/".join(x.lower() if i <= 2 else x for i, x in enumerate(segs))
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                             if not k.lower().startswith(_DROP_PARAMS)))
    return urlunsplit(("https", netloc, path, query, ""))


_GITHUB_REPO = re.compile(r"^(?:git\+)?https?://(?:www\.)?github\.com/([^/?#]+)/([^/?#]+)", re.I)


def github_repo(url: str) -> str | None:
    """github.com/<owner>/<repo>(하위 경로 포함)를 가리키는 URL 이면 소문자 "owner/repo". 아니면 None."""
    m = _GITHUB_REPO.match(url.strip())
    if not m:
        return None
    repo = re.sub(r"(?i)\.git$", "", m.group(2))
    return f"{m.group(1)}/{repo}".lower()


def text_hash(text: str) -> str:
    return hashing.sha256_text(text)[:16]


def _utc(t: datetime) -> str:
    if t.tzinfo is None:
        raise ValueError("가져온 시각은 시간대가 있어야 한다")
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Evidence:
    url: str                  # 쓰여 있던 그대로 — 비교는 key 로
    source: str               # github · hn · web · package · geeknews
    kind: str                 # readme · release · repo · story · comment · search
    title: str
    excerpt: str              # 짧은 인용 (정본에 남는 것)
    fetched_at: str           # ISO 8601 UTC
    content_hash: str         # 원문 해시 앞 16자
    published_at: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)   # 점수·댓글 수 등 출처별 수치
    text: str = field(default="", repr=False)                # 원문 — 기록에는 넣지 않는다

    @property
    def key(self) -> str:
        k = normalize_url(self.url)
        assert k is not None   # make 가 검사했다
        return k

    def record(self) -> dict[str, Any]:
        return {"url": self.url, "source": self.source, "kind": self.kind, "title": self.title,
                "excerpt": self.excerpt, "fetched_at": self.fetched_at, "content_hash": self.content_hash,
                "published_at": self.published_at, "extra": dict(self.extra)}


def make(*, url: str, source: str, kind: str, title: str, text: str, fetched_at: datetime,
         published_at: str | None = None, extra: Mapping[str, Any] | None = None) -> Evidence:
    if normalize_url(url) is None:
        raise ValueError(f"웹 링크가 아니다: {url[:80]!r}")
    excerpt = re.sub(r"\s+", " ", text).strip()[:EXCERPT_CHARS]
    return Evidence(url=url, source=source, kind=kind, title=title.strip(), excerpt=excerpt,
                    fetched_at=_utc(fetched_at), content_hash=text_hash(text), published_at=published_at,
                    extra=dict(extra or {}), text=text)


def from_record(rec: Mapping[str, Any]) -> Evidence:
    return Evidence(url=rec["url"], source=rec["source"], kind=rec["kind"], title=rec["title"],
                    excerpt=rec["excerpt"], fetched_at=rec["fetched_at"], content_hash=rec["content_hash"],
                    published_at=rec.get("published_at"), extra=dict(rec.get("extra") or {}))


def dedupe(docs: Iterable[Evidence]) -> list[Evidence]:
    """정규화한 URL 이 같으면 처음 것만 남긴다 (출처 순서가 우선순위)."""
    seen: set[str] = set()
    out: list[Evidence] = []
    for d in docs:
        if d.key not in seen:
            seen.add(d.key)
            out.append(d)
    return out
