"""stages.backfill — 히스토리 API 로 과거 52주 주간 파일을 1회 만든다 (FR-2.4, 결정 22)."""

from datetime import date, timedelta

from startrend.clients import github_parse as gp
from startrend.clients.github_mock import MockGitHub
from startrend.core import weekfile
from startrend.core.snapshot import SnapRow
from startrend.stages import backfill as bf
from tests import synth

TODAY = date(2026, 10, 26)  # 이번 주 10-25 (진행 중), 지난 주 10-18
CUR = date(2026, 10, 25)


def snap(rid: int, stars: int, created: date) -> SnapRow:
    return SnapRow(rid, f"o/r{rid}", stars, 1, 1, created, ("pool",))


def test_backfill_rows_walk_back_from_current_total():
    weeks = gp.parse_history(synth.history(CUR, [5, 100, 40, 20]))  # 진행 중 5, 그다음부터 완결 주
    rows = bf.week_rows_from_history(snap(1, 1000, date(2020, 1, 1)), weeks, today=TODAY, weeks_back=3)
    assert sorted(rows, reverse=True) == [date(2026, 10, 18), date(2026, 10, 11), date(2026, 10, 4)]
    assert rows[date(2026, 10, 18)].stars_end == 995 and rows[date(2026, 10, 18)].gain == 100
    assert rows[date(2026, 10, 11)].stars_end == 895 and rows[date(2026, 10, 11)].gain == 40
    assert rows[date(2026, 10, 4)].stars_end == 855 and rows[date(2026, 10, 4)].gain == 20
    assert all(r.exact for r in rows.values())


def test_backfill_rows_stop_before_creation_week():
    weeks = gp.parse_history(synth.history(CUR, [5, 100, 40]))
    rows = bf.week_rows_from_history(snap(1, 145, date(2026, 10, 13)), weeks, today=TODAY, weeks_back=10)
    assert sorted(rows) == [date(2026, 10, 11), date(2026, 10, 18)]  # 10-13 생성 → 10-11 주부터


def test_backfill_rows_fast_new_repo_start_not_negative():
    # 회귀(2026-10-26 시험 소급): 역산만 쓰면 10-18 주 끝 20,000 < 증가 22,015, 10-11 주 끝은 0 이 됐다
    weeks = gp.parse_history(synth.history(CUR, [3000, 22015, 300]))
    rows = bf.week_rows_from_history(snap(1, 23000, date(2026, 10, 16)), weeks, today=TODAY, weeks_back=4)
    assert rows[date(2026, 10, 18)].stars_end == 22315
    assert rows[date(2026, 10, 11)].stars_end == 300
    assert all(r.stars_end >= r.gain for r in rows.values())


def _gh(repos: list[tuple[int, int, str, list[int]]]) -> MockGitHub:
    gh = MockGitHub()
    for rid, stars, created, totals in repos:
        gh.add_repo(synth.repo(f"o/r{rid}", id=rid, stars=stars, created=created + "T00:00:00Z"))
        gh.add_history(f"o/r{rid}", synth.history(CUR, totals))
    return gh


def test_backfill_second_page_only_for_old_repos(tmp_path):
    gh = _gh([(1, 5000, "2020-01-01", [1] + [20] * 40), (2, 300, "2026-09-01", [1] + [30] * 8)])
    rows = [snap(1, 5000, date(2020, 1, 1)), snap(2, 300, date(2026, 9, 1))]
    stats = bf.run_backfill(gh, rows=rows, today=TODAY, weeks_back=35, data_dir=tmp_path, log=lambda m: None)
    assert gh.stats.calls["history"] == 3  # r1: 2쪽, r2: 1쪽
    assert stats["repos"] == 2 and stats["history_calls"] == 3


def test_backfill_writes_one_file_per_week_with_gain_rows(tmp_path):
    gh = _gh([(1, 5000, "2020-01-01", [1, 20, 5, 30]), (2, 800, "2020-01-01", [1, 3, 50, 9])])
    rows = [snap(1, 5000, date(2020, 1, 1)), snap(2, 800, date(2020, 1, 1))]
    stats = bf.run_backfill(gh, rows=rows, today=TODAY, weeks_back=3, data_dir=tmp_path, log=lambda m: None)
    w18 = weekfile.read(weekfile.week_path(tmp_path, date(2026, 10, 18)))
    w11 = weekfile.read(weekfile.week_path(tmp_path, date(2026, 10, 11)))
    w04 = weekfile.read(weekfile.week_path(tmp_path, date(2026, 10, 4)))
    assert set(w18) == {1}        # r2 는 3 — 10 미만
    assert set(w11) == {2}        # r1 은 5
    assert set(w04) == {1}        # r2 는 9
    assert stats["weeks_written"] == 3


def test_backfill_existing_week_file_is_kept(tmp_path):
    path = weekfile.week_path(tmp_path, date(2026, 10, 18))
    weekfile.write(path, [weekfile.WeekRow(9, "x/y", date(2020, 1, 1), 1, 99, False, None)])
    gh = _gh([(1, 5000, "2020-01-01", [1, 20])])
    stats = bf.run_backfill(gh, rows=[snap(1, 5000, date(2020, 1, 1))], today=TODAY, weeks_back=1,
                            data_dir=tmp_path, log=lambda m: None)
    assert set(weekfile.read(path)) == {9}
    assert stats["weeks_kept"] == [date(2026, 10, 18).isoformat()]


def test_backfill_target_weeks():
    assert bf.target_weeks(TODAY, 2) == [date(2026, 10, 18), date(2026, 10, 11)]
    assert bf.target_weeks(TODAY, 1)[0] == CUR - timedelta(days=7)


# --- 결정 72: 2026-11-14 주부터 토 ~ 금 ---


def test_backfill_targets_cross_the_cutover():
    # 2026-11-22(일) — 막 끝난 주 11-14 부터 과거로. 11-14 의 앞 주는 11-08(6일 차이)
    want = [date(2026, 11, 14), date(2026, 11, 8), date(2026, 11, 1)]
    assert bf.target_weeks(date(2026, 11, 22), 3) == want


def test_backfill_rows_split_api_weeks_into_new_weeks():
    raw = [{"week": synth.sunday_ts(date(2026, 11, 22)), "total": 5, "days": [5, 0, 0, 0, 0, 0, 0]},
           {"week": synth.sunday_ts(date(2026, 11, 15)), "total": 91, "days": [1, 2, 3, 4, 5, 6, 70]},
           {"week": synth.sunday_ts(date(2026, 11, 8)), "total": 100, "days": [10, 10, 10, 10, 10, 10, 40]}]
    rows = bf.week_rows_from_history(snap(1, 5000, date(2020, 1, 1)), gp.parse_history(raw),
                                     today=date(2026, 11, 22), weeks_back=2)
    assert sorted(rows) == [date(2026, 11, 8), date(2026, 11, 14)]
    new, old = rows[date(2026, 11, 14)], rows[date(2026, 11, 8)]
    assert new.days == (40, 1, 2, 3, 4, 5, 6) and new.gain == 61 and new.stars_end == 5000 - 75
    assert old.days == (10, 10, 10, 10, 10, 10, 40) and old.gain == 100 and old.stars_end == 5000 - 96


def test_backfill_fetches_one_more_api_week_for_new_weeks(tmp_path):
    # 새 주 S 는 API 주 S−6 의 토요일이 필요하다 — 29주 소급에 API 주 31개(이번 API 주 포함)
    gh = MockGitHub()
    gh.add_repo(synth.repo("o/r1", id=1, stars=5000, created="2020-01-01T00:00:00Z"))
    gh.add_history("o/r1", synth.history(date(2026, 11, 22), [1] + [20] * 40))
    stats = bf.run_backfill(gh, rows=[snap(1, 5000, date(2020, 1, 1))], today=date(2026, 11, 22),
                            weeks_back=29, data_dir=tmp_path, log=lambda m: None)
    assert stats["history_calls"] == 2
