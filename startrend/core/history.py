"""스타 히스토리로 주 끝 스타를 추정한다 (SPEC FR-2.6).

두 가지 추정이 있고 둘 다 실제보다 작게 잡힌다.
- 역산: 현재 스타 − target 이후의 주들. 스냅샷을 찍은 뒤 히스토리를 받기까지 늘어난 만큼 작다.
- 누적 합: 히스토리에서 target 까지 더한 값. 히스토리가 생성 시점까지 닿지 않으면 작다.
그래서 큰 쪽을 쓴다. 누적 합에는 target 주의 증가가 들어 있으니 주 시작 스타가 음수가 되지 않는다.
"""

from collections.abc import Sequence
from datetime import date

from startrend.core.models import HistoryWeek


def week_end_stars(weeks: Sequence[HistoryWeek], target: date, *, current_total: int) -> int:
    backward = current_total - sum(w.total for w in weeks if w.week > target)
    forward = sum(w.total for w in weeks if w.week <= target)
    return max(backward, forward, 0)
