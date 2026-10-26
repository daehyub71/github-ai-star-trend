"""stages.rank — 주간 파일에서 4축 랭킹(전체 탭)과 급등 패턴 표시를 만든다 (FR-4, 결정 28)."""

from datetime import date

from startrend.clients.github_mock import MockGitHub
from startrend.core import io, meta, weekfile
from startrend.core.weekfile import WeekRow
from startrend.stages import rank
from tests import synth

W = date(2026, 10, 18)  # 주 끝 10-24
OLD = date(2020, 1, 1)


def row(rid: int, stars_end: int, gain: int, *, created: date = OLD, days: tuple[int, ...] | None = None,
        name: str | None = None) -> WeekRow:
    return WeekRow(rid, name or f"o{rid}/r{rid}", created, stars_end, gain, days is not None, days)


# --- 축 ---


def test_rank_gain_axis_sorted_desc_ties_by_id():
    rows = {1: row(1, 5000, 300), 2: row(2, 9000, 900), 3: row(3, 7000, 300)}
    axes = rank.compute_axes(rows, W, top=3)
    assert [r.id for r in axes["gain"]] == [2, 1, 3]


def test_rank_fresh_axis_only_created_within_30_days_by_stars():
    rows = {1: row(1, 90_000, 50), 2: row(2, 3000, 2000, created=date(2026, 10, 1)),
            3: row(3, 8000, 7000, created=date(2026, 9, 25)),   # 주 끝(10-24)에서 29일 전
            4: row(4, 9000, 50, created=date(2026, 9, 24))}     # 30일 전 — 빠진다
    axes = rank.compute_axes(rows, W, top=5)
    assert [r.id for r in axes["fresh"]] == [3, 2]


def test_rank_growth_axis_requires_start_1000():
    rows = {1: row(1, 1500, 600),     # 시작 900 — 빠진다
            2: row(2, 2000, 800),     # 시작 1200, 66.7%
            3: row(3, 110_000, 10_000)}  # 시작 100,000, 10%
    axes = rank.compute_axes(rows, W, top=5)
    assert [r.id for r in axes["growth"]] == [2, 3]


def test_rank_total_axis_by_stars_end():
    rows = {1: row(1, 500_000, 20), 2: row(2, 900_000, 15), 3: row(3, 10, 10)}
    assert [r.id for r in rank.compute_axes(rows, W, top=2)["total"]] == [2, 1]


def test_rank_total_axis_can_include_low_gain_totals():
    # 주간 파일엔 증가 ≥ 10 만 있다 — 스냅샷이 있으면 증가가 적은 큰 저장소도 누적 축에 넣는다
    rows = {1: row(1, 500_000, 20)}
    extra = {9: (row(9, 800_000, 2))}
    assert [r.id for r in rank.compute_axes(rows, W, top=2, extra_totals=extra)["total"]] == [9, 1]


# --- 급등 패턴 ---


def test_rank_flag_peak_day_share():
    r = row(1, 22556, 22017, created=date(2026, 10, 16), days=(0, 3, 15264, 3401, 1601, 1076, 672))
    flags = rank.flags_for(r, {1: r}, None, W)
    assert {"kind": "peak_day", "label": "하루 몰림 69%", "value": 69} in flags


def test_rank_flag_peak_day_needs_meaningful_gain():
    r = row(1, 100, 20, days=(20, 0, 0, 0, 0, 0, 0))
    assert rank.flags_for(r, {1: r}, None, W) == []


def test_rank_flag_same_owner_new_repos():
    rows = {i: row(i, 5000 + i, 100, created=date(2026, 10, 1), name=f"same/r{i}") for i in range(1, 5)}
    flags = rank.flags_for(rows[1], rows, None, W)
    assert {"kind": "same_owner_new", "label": "같은 계정 새 저장소 4개", "value": 4} in flags


def test_rank_flag_issue_and_fork_ratio_from_repo_info():
    r = row(1, 72917, 6058)
    info = {"forks": 12923, "open_issues": 3127, "stars": 72917}
    kinds = {f["kind"]: f["label"] for f in rank.flags_for(r, {1: r}, info, W)}
    assert kinds == {"issue_ratio": "열린 이슈 4.3%"}  # 포크 17.7% 는 기준(30%) 아래


# --- 실행 ---


def _gh(rows: dict[int, WeekRow]) -> MockGitHub:
    gh = MockGitHub()
    for r in rows.values():
        raw = synth.repo(r.full_name, id=r.id, stars=r.stars_end, description=f"desc {r.id}", topics=["llm"])
        gh.add_repo(raw)
    return gh


def test_rank_run_writes_rankings_and_meta(tmp_path):
    rows = {1: row(1, 5000, 300), 2: row(2, 9000, 900)}
    weekfile.write(weekfile.week_path(tmp_path, W), list(rows.values()))
    gh = _gh(rows)
    stats = rank.run_rank(gh, week_start=W, data_dir=tmp_path, top=15, log=lambda m: None)
    out = io.read_json(rank.rankings_path(tmp_path, W))
    assert out["week"] == "2026-10-18" and out["week_end"] == "2026-10-24"
    gain = out["axes"]["gain"]["all"]
    assert [e["full_name"] for e in gain] == ["o2/r2", "o1/r1"]
    assert gain[0]["rank"] == 1 and gain[0]["description"] == "desc 2" and gain[0]["prev_rank"] is None
    assert out["axes"]["gain"]["ai"] is None  # AI 탭은 Phase 2
    m = meta.load(tmp_path, 2)
    assert m is not None and m["first_seen"] == "2026-10-18" and m["topics"] == ["llm"]
    assert stats["entrants"] == 2 and stats["repo_calls"] == 2


def test_rank_run_reads_previous_week_for_rank_change(tmp_path):
    prev_w = date(2026, 10, 11)
    weekfile.write(weekfile.week_path(tmp_path, prev_w), [row(1, 4700, 500), row(2, 8100, 100)])
    weekfile.write(weekfile.week_path(tmp_path, W), [row(1, 5000, 300), row(2, 9000, 900)])
    gh = _gh({1: row(1, 5000, 300), 2: row(2, 9000, 900)})
    rank.run_rank(gh, week_start=prev_w, data_dir=tmp_path, log=lambda m: None)
    rank.run_rank(gh, week_start=W, data_dir=tmp_path, log=lambda m: None)
    gain = io.read_json(rank.rankings_path(tmp_path, W))["axes"]["gain"]["all"]
    assert [(e["id"], e["rank"], e["prev_rank"]) for e in gain] == [(2, 1, 2), (1, 2, 1)]
    m = meta.load(tmp_path, 1)
    assert m is not None and m["first_seen"] == "2026-10-11"


def test_rank_tracked_names_from_rankings(tmp_path):
    rows = {1: row(1, 5000, 300), 2: row(2, 9000, 900)}
    weekfile.write(weekfile.week_path(tmp_path, W), list(rows.values()))
    rank.run_rank(_gh(rows), week_start=W, data_dir=tmp_path, log=lambda m: None)
    assert rank.tracked_names(tmp_path, W) == ["o1/r1", "o2/r2"]
    assert rank.tracked_names(tmp_path, date(2026, 10, 11)) == []
