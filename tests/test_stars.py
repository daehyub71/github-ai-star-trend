"""stages.stars — 스냅샷 차이로 후보를 고르고, 상위 후보만 히스토리로 정확한 주간 값을 받는다.

FR-2, 결정 27·29.
"""

from datetime import date

from startrend.clients import github_parse as gp
from startrend.clients.github_mock import MockGitHub
from startrend.core import weekfile
from startrend.core.snapshot import SnapRow
from startrend.stages import stars as st
from tests import synth

TODAY = date(2026, 10, 26)  # 월 — 이번 주 10-25, 지난 주 10-18
LAST = date(2026, 10, 18)
OLD = date(2020, 1, 1)


def snap(rid: int, stars: int, *, created: date = OLD, sources: tuple[str, ...] = ("pool",)) -> SnapRow:
    return SnapRow(rid, f"o/r{rid}", stars, stars // 10, 1, created, sources)


# --- exact_week ---


def test_stars_exact_week_subtracts_partial_current_week():
    weeks = gp.parse_history(synth.history(date(2026, 10, 25), [30, 700, 500]))
    e = st.exact_week(weeks, LAST, current_total=5000)
    assert e.gain == 700
    assert e.stars_end == 5000 - 30
    assert len(e.days) == 7 and sum(e.days) == 700


def test_stars_exact_week_older_target_subtracts_weeks_after():
    weeks = gp.parse_history(synth.history(date(2026, 10, 25), [30, 700, 500]))
    e = st.exact_week(weeks, date(2026, 10, 11), current_total=5000)
    assert e.gain == 500
    assert e.stars_end == 5000 - 30 - 700


def test_stars_exact_week_missing_week_is_zero():
    weeks = gp.parse_history(synth.history(date(2026, 10, 25), [30]))
    e = st.exact_week(weeks, LAST, current_total=100)
    assert e.gain == 0 and e.days == (0,) * 7


def test_stars_exact_week_fast_new_repo_start_not_negative():
    # 회귀(2026-10-26 시험 소급, deepseek-ai/DeepInfer): 스냅샷 뒤 히스토리를 받기까지 진행 중인 주가 커져
    # 역산한 주 끝 스타(20,000)가 그 주 증가(22,015)보다 작았다 → 주 시작 스타가 음수
    weeks = gp.parse_history(synth.history(date(2026, 10, 25), [3000, 22015, 300]))
    e = st.exact_week(weeks, LAST, current_total=23000)
    assert e.gain == 22015
    assert e.stars_end == 300 + 22015  # 히스토리 누적 합이 더 크다 — 그쪽을 쓴다
    assert e.stars_end - e.gain >= 0


# --- select_candidates ---


def test_stars_select_by_gain_growth_new_and_tracked():
    prev = {1: snap(1, 100_000), 2: snap(2, 1000), 3: snap(3, 50_000), 4: snap(4, 900)}
    cur = {
        1: snap(1, 105_000),   # 증가 5,000 — 증가량 1위
        2: snap(2, 1_500),     # 증가 500, 성장률 50% — 성장률 1위
        3: snap(3, 50_100),    # 증가 100
        4: snap(4, 2_000),     # 시작 900 < 1,000 — 성장률 후보 아님, 증가 1,100 은 증가량 2위
        5: snap(5, 3_000, created=date(2026, 10, 20), sources=("new",)),
        6: snap(6, 40),        # 추적
    }
    picked = st.select_candidates(cur, prev, top_gain=2, top_growth=1, top_new=5, tracked=["o/r6"])
    assert [s.id for s in picked] == [1, 4, 2, 5, 6]


def test_stars_select_without_prev_uses_fallback():
    cur = {1: snap(1, 9000), 2: snap(2, 8000), 3: snap(3, 50, created=date(2026, 10, 20), sources=("new",))}
    picked = st.select_candidates(cur, None, top_new=5, fallback_top=1)
    assert [s.id for s in picked] == [1, 3]


# --- build_rows ---


def test_stars_build_rows_exact_overrides_snapshot_diff():
    prev = {1: snap(1, 1000), 2: snap(2, 2000)}
    cur = {1: snap(1, 1200), 2: snap(2, 2050), 3: snap(3, 500, created=date(2026, 10, 20), sources=("new",))}
    exact = {1: st.Exact(gain=180, days=(10, 20, 30, 40, 50, 20, 10), stars_end=1190)}
    rows = {r.id: r for r in st.build_rows(cur, prev, exact)}
    assert rows[1].exact and rows[1].gain == 180 and rows[1].stars_end == 1190
    assert not rows[2].exact and rows[2].gain == 50 and rows[2].days is None
    assert 3 not in rows  # 지난 주 값도 정밀 값도 없으면 증가량을 모른다


# --- run_stars ---


def _gh_for(cur: dict[int, SnapRow]) -> MockGitHub:
    gh = MockGitHub()
    for s in cur.values():
        gh.add_repo(synth.repo(s.full_name, id=s.id, stars=s.stars))
        gh.add_history(s.full_name, synth.history(date(2026, 10, 25), [7, 210, 70]))
    return gh


def test_stars_run_writes_week_file(tmp_path):
    prev = {1: snap(1, 1000), 2: snap(2, 5000)}
    cur = {1: snap(1, 1217), 2: snap(2, 5004)}
    gh = _gh_for(cur)
    stats = st.run_stars(gh, cur=cur, prev=prev, week_start=LAST, today=TODAY, data_dir=tmp_path,
                         top_gain=1, top_growth=0, top_new=0, log=lambda m: None)
    path = weekfile.week_path(tmp_path, LAST)
    rows = weekfile.read(path)
    assert set(rows) == {1}  # r2 는 증가 4 — 10 미만이라 빠진다
    assert rows[1].exact and rows[1].gain == 210 and rows[1].stars_end == 1217 - 7
    assert stats["candidates"] == 1 and stats["exact"] == 1 and stats["written"] is True
    assert gh.stats.calls["history"] == 1


def test_stars_run_skips_when_week_file_exists(tmp_path):
    cur = {1: snap(1, 1217)}
    path = weekfile.week_path(tmp_path, LAST)
    weekfile.write(path, [weekfile.WeekRow(1, "o/r1", OLD, 1210, 210, True, (30,) * 7)])
    gh = _gh_for(cur)
    stats = st.run_stars(gh, cur=cur, prev={1: snap(1, 1000)}, week_start=LAST, today=TODAY,
                         data_dir=tmp_path, log=lambda m: None)
    assert stats["written"] is False and stats["reason"] == "exists"
    assert gh.stats.calls.get("history", 0) == 0
