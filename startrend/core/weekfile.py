"""git 에 남는 주간 스타 파일 `data/stars/YYYY/<주 시작일>.csv` (SPEC FR-2.2, 결정 29).

- 주간 증가 ≥ min_gain 인 행만 쓴다. 전체 스냅샷은 Releases(Phase 5 전까지는 .work/snapshots/).
- exact = 1 이면 히스토리 API 의 달력 주 값과 요일별 수(일~토), 0 이면 스냅샷 차이(순증가)다.
- 생성일을 함께 남겨, 스냅샷 없이 이 파일만으로 그 주의 4축 랭킹을 다시 계산할 수 있다.
- 한 번 쓰면 다시 쓰지 않는다(NFR-5 ②).
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from startrend.core import io, week

HEADER = "id,full_name,created,stars_end,gain,exact,d0,d1,d2,d3,d4,d5,d6"
MIN_GAIN = 10


@dataclass(frozen=True)
class WeekRow:
    id: int
    full_name: str
    created: date
    stars_end: int  # 주 마지막 시점 스타 (exact 가 아니면 실행 시점 스냅샷 값)
    gain: int
    exact: bool
    days: tuple[int, ...] | None  # exact 일 때만, 일요일부터 7개


def week_path(data_dir: Path, start: date) -> Path:
    return data_dir / "stars" / str(start.year) / f"{week.week_name(start)}.csv"


def format_rows(rows: list[WeekRow], min_gain: int = MIN_GAIN) -> str:
    lines = [HEADER]
    for r in sorted((r for r in rows if r.gain >= min_gain), key=lambda x: x.id):
        days = ",".join(str(d) for d in r.days) if r.days else ",,,,,,"
        lines.append(f"{r.id},{r.full_name},{r.created.isoformat()},{r.stars_end},{r.gain},"
                     f"{1 if r.exact else 0},{days}")
    return "\n".join(lines) + "\n"


def write(path: Path, rows: list[WeekRow], min_gain: int = MIN_GAIN) -> bool:
    return io.write_immutable(path, format_rows(rows, min_gain))


def read(path: Path) -> dict[int, WeekRow]:
    lines = io.read_text(path).splitlines()
    if not lines or lines[0] != HEADER:
        raise ValueError(f"주간 파일 머리글이 다르다: {path}")
    out: dict[int, WeekRow] = {}
    for line in lines[1:]:
        if not line:
            continue
        f = line.split(",")
        exact = f[5] == "1"
        out[int(f[0])] = WeekRow(
            id=int(f[0]), full_name=f[1], created=date.fromisoformat(f[2]), stars_end=int(f[3]),
            gain=int(f[4]), exact=exact, days=tuple(int(x) for x in f[6:13]) if exact else None,
        )
    return out
