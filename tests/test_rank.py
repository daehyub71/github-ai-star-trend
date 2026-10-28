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
    flags = rank.flags_for(r, {1: r}, W)
    assert {"kind": "peak_day", "label": "하루 몰림 69%", "value": 69} in flags


def test_rank_flag_peak_day_needs_meaningful_gain():
    r = row(1, 100, 20, days=(20, 0, 0, 0, 0, 0, 0))
    assert rank.flags_for(r, {1: r}, W) == []


def test_rank_flag_same_owner_new_repos():
    rows = {i: row(i, 5000 + i, 100, created=date(2026, 10, 1), name=f"same/r{i}") for i in range(1, 5)}
    flags = rank.flags_for(rows[1], rows, W)
    assert {"kind": "same_owner_new", "label": "같은 계정 새 저장소 4개", "value": 4} in flags


def test_rank_flag_dormant_burst():
    # 시험 소급(MEASURE §13)의 morluto/rea — 2026-04 생성, 4주 동안 396 → 379,884
    r = row(1, 379_884, 69_361, created=date(2026, 4, 14))
    flags = rank.flags_for(r, {1: r}, W, prior_gain=145 + 77_992 + 231_990)
    assert flags == [{"kind": "dormant_burst", "label": "잠잠하다 4주 만에 959배", "value": 959.3}]


def test_rank_flag_dormant_burst_skips_young_repo():
    # 생성 60일 미만은 원래 폭발적으로 큰다 — 같은 계정·하루 몰림 표시가 따로 본다
    r = row(1, 32_520, 32_023, created=date(2026, 10, 17))
    assert rank.flags_for(r, {1: r}, W, prior_gain=497) == []


def test_rank_flag_dormant_burst_skips_large_start():
    r = row(1, 80_000, 30_000, created=date(2025, 1, 1))  # 4주 전 5,000 이상
    assert rank.flags_for(r, {1: r}, W, prior_gain=40_000) == []


def test_rank_flag_dormant_burst_skips_launch_from_zero():
    # 결정 49: 4주 전 스타가 100 미만이면 만들어 두었다가 공개·출시한 경우가 대부분이다
    # (MEASURE §16 — andrewyng/context-hub 0 → 11,125 · cloudflare · facebook · NVIDIA …)
    r = row(1, 11_125, 9_000, created=date(2025, 10, 30))
    assert rank.flags_for(r, {1: r}, W, prior_gain=2_125) == []


def test_rank_flag_dormant_burst_start_boundary_100():
    r = row(1, 5_000, 3_000, created=date(2025, 1, 1))
    assert rank.flags_for(r, {1: r}, W, prior_gain=1_901) == []  # 4주 전 99
    hit = rank.flags_for(r, {1: r}, W, prior_gain=1_900)  # 4주 전 100 → 50배
    assert hit == [{"kind": "dormant_burst", "label": "잠잠하다 4주 만에 50배", "value": 50.0}]


def test_rank_flag_dormant_burst_needs_full_window():
    r = row(1, 379_884, 69_361, created=date(2026, 4, 14))
    assert rank.flags_for(r, {1: r}, W) == []  # 지난 3주 값이 없으면 판단하지 않는다


def test_rank_prior_gains_none_when_a_week_file_is_missing(tmp_path):
    for w, g in ((date(2026, 10, 4), 77_992), (date(2026, 10, 11), 231_990)):
        weekfile.write(weekfile.week_path(tmp_path, w), [row(1, 1000, g)])
    assert rank.prior_gains(tmp_path, W) is None  # 09-27 주 파일이 없다
    weekfile.write(weekfile.week_path(tmp_path, date(2026, 9, 27)), [row(1, 1000, 145), row(2, 50, 12)])
    assert rank.prior_gains(tmp_path, W) == {1: 145 + 77_992 + 231_990, 2: 12}


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


def test_rank_run_marks_dormant_burst_with_full_window(tmp_path):
    created = date(2026, 4, 14)
    for w, end, g in ((date(2026, 9, 27), 541, 145), (date(2026, 10, 4), 78_533, 77_992),
                      (date(2026, 10, 11), 310_523, 231_990)):
        weekfile.write(weekfile.week_path(tmp_path, w), [row(1, end, g, created=created)])
    cur = row(1, 379_884, 69_361, created=created)
    weekfile.write(weekfile.week_path(tmp_path, W), [cur])
    rank.run_rank(_gh({1: cur}), week_start=W, data_dir=tmp_path, log=lambda m: None)
    entry = io.read_json(rank.rankings_path(tmp_path, W))["axes"]["gain"]["all"][0]
    assert [f["kind"] for f in entry["flags"]] == ["dormant_burst"]


def test_rank_run_keeps_issue_and_fork_counts_without_flags(tmp_path):
    # 결정 49: 이슈·포크 비율은 52주에서 정상 저장소가 대부분(MEASURE §16) — 수치만 남기고 표시하지 않는다
    r = row(1, 2694, 900)
    weekfile.write(weekfile.week_path(tmp_path, W), [r])
    gh = MockGitHub()
    raw = synth.repo(r.full_name, id=1, stars=2694)
    raw["open_issues_count"], raw["forks_count"] = 975, 2233  # 36% · 83%
    gh.add_repo(raw)
    rank.run_rank(gh, week_start=W, data_dir=tmp_path, log=lambda m: None)
    e = io.read_json(rank.rankings_path(tmp_path, W))["axes"]["gain"]["all"][0]
    assert e["flags"] == [] and (e["open_issues"], e["forks"]) == (975, 2233)


# --- AI 탭 (P2-6, FR-4.5) ---


def _judge(data_dir, rid: int, *, ai: bool | None, cat: str = "rag", status: str = "ok") -> None:
    ok = status == "ok"
    meta.save(data_dir, {"id": rid, "full_name": f"o{rid}/r{rid}", "classify": {
        "status": status, "is_ai": ai if ok else None, "type": "도구/라이브러리" if ok else None,
        "category": cat if (ok and ai) else None, "secondary": None}})


def _six(tmp_path) -> dict[int, WeekRow]:
    rows = {i: row(i, 5000 + 100 * i, 100 * i) for i in range(1, 7)}   # 증가 순서: 6 > 5 > … > 1
    weekfile.write(weekfile.week_path(tmp_path, W), list(rows.values()))
    return rows


def test_rank_ai_tab_takes_ai_repos_in_axis_order(tmp_path):
    rows = _six(tmp_path)
    for i, ai in ((6, False), (5, True), (4, False), (3, True), (2, True), (1, False)):
        _judge(tmp_path, i, ai=ai, cat="mcp-tools" if i == 3 else "rag")
    rank.run_rank(_gh(rows), week_start=W, data_dir=tmp_path, top=2, log=lambda m: None)
    out = io.read_json(rank.rankings_path(tmp_path, W))
    gain = out["axes"]["gain"]
    assert [e["id"] for e in gain["all"]] == [6, 5]
    assert [(e["id"], e["rank"], e["category"]) for e in gain["ai"]] == [(5, 1, "rag"), (3, 2, "mcp-tools")]
    # 전체 탭 항목에도 판정 결과가 붙는다 — 화면의 카테고리·유형 칩
    assert gain["all"][0]["is_ai"] is False and gain["all"][1]["type"] == "도구/라이브러리"
    assert out["ai_status"]["gain"] == {"found": 2, "pending_above": 0}


def test_rank_ai_tab_counts_pending_candidates_above_the_cut(tmp_path):
    # 15번째 AI 보다 위에 아직 판정 안 된 후보가 있으면, 그것이 AI 일 때 순위가 바뀐다 — 그 수를 남긴다
    rows = _six(tmp_path)
    _judge(tmp_path, 5, ai=True)
    _judge(tmp_path, 4, ai=None, status="refused")      # 거절로 끝난 판정은 대기가 아니다
    _judge(tmp_path, 2, ai=True)
    rank.run_rank(_gh(rows), week_start=W, data_dir=tmp_path, top=2, log=lambda m: None)
    out = io.read_json(rank.rankings_path(tmp_path, W))
    assert [e["id"] for e in out["axes"]["gain"]["ai"]] == [5, 2]
    assert out["ai_status"]["gain"] == {"found": 2, "pending_above": 2}   # 6 과 3


def test_rank_ai_tab_prev_rank_comes_from_last_weeks_ai_tab(tmp_path):
    prev_w = date(2026, 10, 11)
    weekfile.write(weekfile.week_path(tmp_path, prev_w),
                   [row(1, 4700, 500), row(2, 8100, 100), row(3, 3000, 50)])
    cur = {1: row(1, 5000, 300), 2: row(2, 9000, 900), 3: row(3, 3100, 100)}
    weekfile.write(weekfile.week_path(tmp_path, W), list(cur.values()))
    _judge(tmp_path, 1, ai=True)
    _judge(tmp_path, 2, ai=False)
    _judge(tmp_path, 3, ai=True)
    gh = _gh(cur)
    rank.run_rank(gh, week_start=prev_w, data_dir=tmp_path, top=2, log=lambda m: None)
    rank.run_rank(gh, week_start=W, data_dir=tmp_path, top=2, log=lambda m: None)
    gain = io.read_json(rank.rankings_path(tmp_path, W))["axes"]["gain"]
    assert [(e["id"], e["rank"], e["prev_rank"]) for e in gain["ai"]] == [(1, 1, 1), (3, 2, 2)]
    assert [(e["id"], e["prev_rank"]) for e in gain["all"]] == [(2, 2), (1, 1)]


def test_rank_ai_tab_stays_null_before_any_classification(tmp_path):
    rows = _six(tmp_path)
    rank.run_rank(_gh(rows), week_start=W, data_dir=tmp_path, top=2, log=lambda m: None)
    out = io.read_json(rank.rankings_path(tmp_path, W))
    assert out["axes"]["gain"]["ai"] is None and out["ai_status"] is None
    assert out["axes"]["gain"]["all"][0]["is_ai"] is None


def test_rank_tracked_names_from_rankings(tmp_path):
    rows = {1: row(1, 5000, 300), 2: row(2, 9000, 900)}
    weekfile.write(weekfile.week_path(tmp_path, W), list(rows.values()))
    rank.run_rank(_gh(rows), week_start=W, data_dir=tmp_path, log=lambda m: None)
    assert rank.tracked_names(tmp_path, W) == ["o1/r1", "o2/r2"]
    assert rank.tracked_names(tmp_path, date(2026, 10, 11)) == []


def test_rank_run_writes_deeper_candidate_pool_per_axis(tmp_path):
    # classify 는 축마다 위에서부터 AI 15개가 찰 때까지 내려간다(결정 30) — rank 가 더 깊은 순서를 남긴다
    rows = {i: row(i, 2000 + i * 10, 100 + i) for i in range(1, 21)}
    weekfile.write(weekfile.week_path(tmp_path, W), list(rows.values()))
    rank.run_rank(_gh(rows), week_start=W, data_dir=tmp_path, top=3, pool=10, log=lambda m: None)
    out = io.read_json(rank.rankings_path(tmp_path, W))
    gain_pool = out["pool"]["gain"]
    assert gain_pool == list(range(20, 10, -1))                      # 증가 큰 순 10개
    assert [e["id"] for e in out["axes"]["gain"]["all"]] == gain_pool[:3]
    assert set(out["pool"]) == set(rank.AXES)
