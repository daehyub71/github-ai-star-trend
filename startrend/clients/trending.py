"""GitHub Trending 페이지 — probe 의 대조 출처로만 쓴다.

공식 API 가 없어 운영 의존으로 두지 않는다 (SPEC R11).

페이지 구조는 2026-10-26 기준이다. 구조가 바뀌면 parse_trending 이 빈 목록을 돌려주고,
probe 가 그대로 보고한다.
"""

import re
from dataclasses import dataclass

from startrend.clients.transport import Transport

_ROW = re.compile(r'<article class="Box-row">(.*?)</article>', re.S)
_NAME = re.compile(r'<h2[^>]*>\s*<a[^>]*?href="/([^/"?]+/[^/"?]+)"', re.S)
_TOTAL = re.compile(r'href="/[^/"]+/[^/"]+/stargazers"[^>]*>.*?</svg>\s*([\d,]+)\s*</a>', re.S)
_PERIOD = re.compile(r"([\d,]+)\s+stars\s+(?:this\s+week|today|this\s+month)")


@dataclass(frozen=True)
class TrendingRepo:
    full_name: str
    stars_total: int | None
    stars_period: int  # 기간(주간·일간·월간) 동안 받은 스타 — GitHub 자체 산출값


def trending_url(since: str = "weekly") -> str:
    return f"https://github.com/trending?since={since}"


def parse_trending(html: str) -> list[TrendingRepo]:
    out = []
    for block in _ROW.findall(html):
        name = _NAME.search(block)
        period = _PERIOD.search(block)
        if not name or not period:
            continue
        total = _TOTAL.search(block)
        out.append(TrendingRepo(
            full_name=name.group(1),
            stars_total=_num(total.group(1)) if total else None,
            stars_period=_num(period.group(1)),
        ))
    return out


def fetch_trending(transport: Transport, since: str = "weekly", timeout: float = 30.0) -> str:
    headers = {"User-Agent": "startrend/0.0.1", "Accept": "text/html"}
    resp = transport("GET", trending_url(since), headers, timeout)
    if resp.status != 200:
        raise RuntimeError(f"trending HTTP {resp.status}")
    return resp.body.decode("utf-8", errors="replace")


def _num(s: str) -> int:
    return int(s.replace(",", ""))
