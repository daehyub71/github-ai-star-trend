"""core.weekfile — git 에 남는 주간 스타 파일 (FR-2.2, 결정 29: 주간 증가 ≥ 10 인 행만, 한 번 쓰면 그대로)."""

from datetime import date
from pathlib import Path

import pytest

from startrend.core import io, weekfile
from startrend.core.weekfile import WeekRow

W = date(2026, 10, 18)


def _rows():
    return [
        WeekRow(3, "c/c", date(2026, 10, 16), 22556, 22017, True, (0, 3, 15264, 3401, 1601, 1076, 672)),
        WeekRow(1, "a/a", date(2020, 1, 1), 5000, 9, False, None),  # 증가 9 — 빠진다
        WeekRow(2, "b/b", date(2021, 5, 5), 1200, 10, False, None),
    ]


def test_weekfile_path_by_year():
    assert weekfile.week_path(Path("data"), W) == Path("data/stars/2026/2026-10-18.csv")


def test_weekfile_keeps_only_gain_at_least_min_sorted_by_id():
    text = weekfile.format_rows(_rows(), min_gain=10)
    lines = text.splitlines()
    assert lines[0] == weekfile.HEADER
    assert [line.split(",")[0] for line in lines[1:]] == ["2", "3"]


def test_weekfile_round_trip(tmp_path):
    p = tmp_path / "w.csv"
    weekfile.write(p, _rows(), min_gain=10)
    back = weekfile.read(p)
    assert set(back) == {2, 3}
    assert back[3].days == (0, 3, 15264, 3401, 1601, 1076, 672)
    assert back[3].exact is True and back[2].exact is False and back[2].days is None
    assert back[3].created == date(2026, 10, 16)


def test_weekfile_is_immutable(tmp_path):
    p = tmp_path / "w.csv"
    weekfile.write(p, _rows(), min_gain=10)
    assert weekfile.write(p, _rows(), min_gain=10) is False  # 같은 내용 재실행은 조용히 넘어간다
    changed = [WeekRow(2, "b/b", date(2021, 5, 5), 1300, 110, False, None)]
    with pytest.raises(io.ImmutableFileError):
        weekfile.write(p, changed, min_gain=10)


def test_weekfile_rejects_bad_header(tmp_path):
    p = tmp_path / "w.csv"
    p.write_text("x,y\n", encoding="utf-8")
    with pytest.raises(ValueError):
        weekfile.read(p)


def test_weekfile_row_size_is_small():
    # 1MB 크기 가드 안에 들어가는지 가늠 — 한 줄 약 40~80바이트
    line = weekfile.format_rows([_rows()[0]], min_gain=10).splitlines()[1]
    assert len(line.encode()) < 90
