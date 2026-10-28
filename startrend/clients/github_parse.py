"""GitHub API JSON → 모델. 순수 함수이고, mock 과 live 가 같이 쓴다.

형식이 예상과 다르면 조용히 넘어가지 않고 GitHubFormatError 를 낸다.
"""

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from startrend.core import week
from startrend.core.models import HistoryWeek, RateLimit, Release, Repo, SearchPage


class GitHubFormatError(Exception):
    pass


def parse_repo(d: Mapping[str, Any]) -> Repo:
    try:
        return Repo(
            id=int(d["id"]),
            full_name=str(d["full_name"]),
            description=d.get("description"),
            topics=tuple(d.get("topics") or ()),
            language=d.get("language"),
            stars=int(d["stargazers_count"]),
            forks=int(d.get("forks_count") or 0),
            open_issues=int(d.get("open_issues_count") or 0),
            created_at=_dt(d["created_at"]),
            pushed_at=_dt(d["pushed_at"]) if d.get("pushed_at") else None,
            archived=bool(d.get("archived", False)),
            is_fork=bool(d.get("fork", False)),
            license=(d.get("license") or {}).get("spdx_id") or None,
            homepage=d.get("homepage") or None,
            has_issues=bool(d.get("has_issues", True)),
        )
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise GitHubFormatError(f"저장소 형식 오류: {e!r}") from e


def parse_releases(raw: Any) -> list[Release]:
    """릴리스 목록(최신 먼저). 초안(draft)은 공개된 것이 아니라 뺀다."""
    if not isinstance(raw, list):
        raise GitHubFormatError(f"릴리스는 배열이어야 한다: {type(raw).__name__}")
    out = []
    for d in raw:
        try:
            if d.get("draft"):
                continue
            tag = str(d["tag_name"])
            out.append(Release(
                tag=tag, name=str(d.get("name") or tag),
                published_at=_dt(d["published_at"]) if d.get("published_at") else None,
                url=str(d["html_url"]), body=str(d.get("body") or ""), prerelease=bool(d.get("prerelease")),
            ))
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise GitHubFormatError(f"릴리스 형식 오류: {e!r}") from e
    return out


def last_page(link: str | None) -> int | None:
    """Link 헤더의 rel="last" 쪽 번호 — 목록 전체 개수를 per_page=1 로 셀 때 쓴다."""
    m = re.search(r'<[^>]*[?&]page=(\d+)[^>]*>;\s*rel="last"', link or "")
    return int(m.group(1)) if m else None


def parse_search_page(d: Mapping[str, Any]) -> SearchPage:
    try:
        return SearchPage(
            total_count=int(d["total_count"]),
            incomplete_results=bool(d.get("incomplete_results", False)),
            items=tuple(parse_repo(item) for item in d["items"]),
        )
    except (KeyError, TypeError, ValueError) as e:
        raise GitHubFormatError(f"검색 결과 형식 오류: {e!r}") from e


def parse_history(raw: Any) -> list[HistoryWeek]:
    if not isinstance(raw, list):
        raise GitHubFormatError(f"히스토리는 배열이어야 한다: {type(raw).__name__}")
    out = []
    for item in raw:
        try:
            ts = int(item["week"])
            days = tuple(int(x) for x in item["days"])
            if len(days) != 7:
                raise ValueError(f"days 는 7개여야 한다: {len(days)}")
            out.append(HistoryWeek(
                week=week.from_api_timestamp(ts),
                total=int(item["total"]),
                days=days,
                raw_ts=ts,
                utc_offset_hours=week.utc_offset_hours(ts),
            ))
        except (KeyError, TypeError, ValueError) as e:
            raise GitHubFormatError(f"히스토리 주 형식 오류: {e!r}") from e
    return out


def parse_rate_limit(headers: Mapping[str, str]) -> RateLimit:
    return RateLimit(
        resource=headers.get("x-ratelimit-resource"),
        limit=_int_or_none(headers.get("x-ratelimit-limit")),
        remaining=_int_or_none(headers.get("x-ratelimit-remaining")),
        reset_at=_int_or_none(headers.get("x-ratelimit-reset")),
    )


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _int_or_none(v: str | None) -> int | None:
    return int(v) if v else None
