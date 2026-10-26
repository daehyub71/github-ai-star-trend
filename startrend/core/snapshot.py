"""전체 스냅샷 — 후보군 저장소의 스타 수를 주 1회 찍어 둔 것 (SPEC FR-1.4, 결정 29).

Phase 5 전까지는 `.work/snapshots/<주>.csv`, 이후에는 Releases `snapshot-<주>.csv.gz`.
지난 주 스냅샷과의 차이가 주간 증가량 후보의 기준이다.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from startrend.core import io

HEADER = "id,full_name,stars,forks,open_issues,created,sources"


@dataclass(frozen=True)
class SnapRow:
    id: int
    full_name: str
    stars: int
    forks: int
    open_issues: int
    created: date
    sources: tuple[str, ...]  # pool · new · tracked


def write(path: Path, rows: Iterable[SnapRow]) -> None:
    lines = [HEADER]
    for r in sorted(rows, key=lambda x: x.id):
        lines.append(f"{r.id},{r.full_name},{r.stars},{r.forks},{r.open_issues},{r.created.isoformat()},"
                     f"{'|'.join(r.sources)}")
    io.write_text_atomic(path, "\n".join(lines) + "\n")


def read(path: Path) -> dict[int, SnapRow]:
    lines = io.read_text(path).splitlines()
    if not lines or lines[0] != HEADER:
        raise ValueError(f"스냅샷 머리글이 다르다: {path}")
    out: dict[int, SnapRow] = {}
    for line in lines[1:]:
        if not line:
            continue
        rid, name, stars, forks, issues, created, srcs = line.split(",")
        out[int(rid)] = SnapRow(int(rid), name, int(stars), int(forks), int(issues),
                                date.fromisoformat(created), tuple(s for s in srcs.split("|") if s))
    return out
