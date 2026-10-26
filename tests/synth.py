"""합성 데이터 생성기. 실제 저장소·실제 자료에 의존하지 않는다 (워크스페이스 TDD 규칙)."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures"


def sunday_ts(d: date, utc_offset_hours: float = 0.0) -> int:
    """그 일요일 0시(지정 시간대)의 유닉스 타임스탬프."""
    midnight = datetime(d.year, d.month, d.day, tzinfo=UTC)
    return int((midnight - timedelta(hours=utc_offset_hours)).timestamp())


def history(newest: date, totals: list[int], utc_offset_hours: float = 0.0) -> list[dict[str, Any]]:
    """히스토리 API 형식. totals[0] 이 newest 주이고 과거로 간다(최신 주 먼저)."""
    out = []
    for i, total in enumerate(totals):
        start = newest - timedelta(days=7 * i)
        base, rest = divmod(total, 7)
        days = [base + (1 if j < rest else 0) for j in range(7)]
        out.append({"week": sunday_ts(start, utc_offset_hours), "total": total, "days": days})
    return out


def repo(full_name: str, *, id: int, stars: int, created: str = "2025-01-01T00:00:00Z",
         description: str | None = "synthetic", topics: list[str] | None = None) -> dict[str, Any]:
    """저장소 API 형식 (필요한 필드만)."""
    return {
        "id": id,
        "full_name": full_name,
        "description": description,
        "topics": topics or [],
        "language": "Python",
        "stargazers_count": stars,
        "forks_count": stars // 10,
        "open_issues_count": 1,
        "created_at": created,
        "pushed_at": created,
        "archived": False,
        "fork": False,
    }
