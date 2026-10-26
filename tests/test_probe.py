"""stages.probe — 실측 (FR-12). 분석 함수는 순수 함수로 검증하고, 전체 흐름은 mock 으로 한 번 돌린다."""

import random
from datetime import UTC, date, datetime

import pytest

from startrend.clients import github_parse as gp
from startrend.clients.github_mock import MockGitHub
from startrend.core.models import Repo
from startrend.stages import probe
from tests import synth

TODAY = date(2026, 10, 26)  # 월요일 — 이번 주 2026-10-25, 지난 주 2026-10-18


def _weeks(totals: list[int], newest: date = date(2026, 10, 25)):
    return gp.parse_history(synth.history(newest, totals))


def _repo(stars: int, created: str = "2024-01-01T00:00:00Z", desc: str | None = "x",
          topics: tuple[str, ...] = ()) -> Repo:
    return gp.parse_repo({**synth.repo("a/b", id=1, stars=stars, created=created, description=desc),
                          "topics": list(topics)})


# --- week_stats ---


def test_probe_week_stats_with_current_partial_week():
    s = probe.week_stats(_weeks([30, 700, 500, 400, 300]), current_total=5000, today=TODAY)
    assert s.partial == 30
    assert s.last_full_gain == 700
    assert s.mean4 == pytest.approx((700 + 500 + 400 + 300) / 4)
    assert s.start_stars == 5000 - 30 - 700
    assert s.growth == pytest.approx(700 / 4270)


def test_probe_week_stats_without_current_week():
    # API 가 진행 중인 주를 아직 안 줄 수도 있다 — 그러면 부분값은 0
    s = probe.week_stats(_weeks([700, 500], newest=date(2026, 10, 18)), current_total=1200, today=TODAY)
    assert (s.partial, s.last_full_gain) == (0, 700)


def test_probe_week_stats_zero_start_has_no_growth():
    s = probe.week_stats(_weeks([0, 50]), current_total=50, today=TODAY)
    assert s.start_stars == 0 and s.growth is None


# --- 표본 · 추정 ---


def test_probe_sample_star_values_distinct_and_in_range():
    vals = probe.sample_star_values(100, 199, 20, random.Random(1))
    assert len(vals) == 20 == len(set(vals))
    assert all(100 <= v <= 199 for v in vals)


def test_probe_sample_star_values_small_range():
    assert sorted(probe.sample_star_values(5, 7, 10, random.Random(1))) == [5, 6, 7]


def test_probe_bucket_query():
    assert probe.bucket_query((100, 199)) == "stars:100..199"
    assert probe.bucket_query((50000, None)) == "stars:>=50000"


def test_probe_estimate_counts_weights_by_bucket_size():
    counts: dict[probe.Bucket, int] = {(100, 199): 1000, (200, 499): 100}
    gains: dict[probe.Bucket, list[int]] = {(100, 199): [0, 0, 0, 600], (200, 499): [600, 600]}
    est = probe.estimate_counts(counts, gains, [500])
    assert est[500] == pytest.approx(1000 * 0.25 + 100 * 1.0)


def test_probe_percentiles():
    p = probe.percentiles([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], [50, 90])
    assert p == {50: 5.5, 90: 9.1}


def test_probe_percentiles_empty():
    assert probe.percentiles([], [50]) == {50: None}


def test_probe_coverage_by_current_stars_or_age():
    rows = [
        {"stars": 5000, "created_at": "2020-01-01T00:00:00+00:00"},
        {"stars": 300, "created_at": "2026-10-20T00:00:00+00:00"},  # 새 저장소
        {"stars": 300, "created_at": "2020-01-01T00:00:00+00:00"},  # 작고 오래됨 → 1000 기준이면 빠짐
    ]
    cov = probe.coverage(rows, thresholds=[1000], new_days=30, today=TODAY)
    assert cov[1000] == pytest.approx(2 / 3)


def test_probe_estimate_tokens():
    assert probe.estimate_tokens("a" * 400) == 100
    assert probe.estimate_tokens("한" * 30) == 20  # 한글은 글자당 더 많은 토큰 — 대략치


def test_probe_looks_ai_keyword_heuristic():
    assert probe.looks_ai(_repo(10, desc="An LLM agent framework"))
    assert probe.looks_ai(_repo(10, desc=None, topics=("mcp",)))
    assert not probe.looks_ai(_repo(10, desc="CSS grid notes"))
    assert not probe.looks_ai(_repo(10, desc="email domain validator"))  # 'ai' 부분 문자열에 속지 않는다


def test_probe_enumeration_calls():
    # 저장소 N 개를 Search 로 열거하려면 대략 N/100 쪽 + 구간 분할 여분
    assert probe.enumeration_calls(25_000) == 250


# --- 전체 흐름 (mock) ---


def test_probe_run_with_mock(tmp_path):
    gh = MockGitHub()
    names = []
    for i in range(30):
        n = f"synth/r{i}"
        names.append(n)
        created = "2026-10-10T00:00:00Z" if i < 3 else "2023-01-01T00:00:00Z"
        gh.add_repo(synth.repo(n, id=i + 1, stars=150 + i, created=created,
                               description="llm agent" if i % 2 else "web"))
        gh.add_history(n, synth.history(date(2026, 10, 25), [5, 20 + i, 10, 10, 10]))
        gh.add_readme(n, "# readme " + "x" * 100)
    gh.add_search("stars:100..199", names)
    gh.add_search("stars:>=100", names)
    html = (synth.FIXTURES / "trending" / "weekly.html").read_text(encoding="utf-8")
    gh.add_repo(synth.repo("synth-lab/agent-kit", id=900, stars=48210, created="2026-10-01T00:00:00Z"))
    gh.add_history("synth-lab/agent-kit", synth.history(date(2026, 10, 25), [3000, 15000]))
    gh.add_repo(synth.repo("synth-lab/mcp-files", id=901, stars=1830))
    gh.add_history("synth-lab/mcp-files", synth.history(date(2026, 10, 25), [100, 700]))

    report = probe.run_probe(gh, fetch_html=lambda url: html, today=TODAY, out_dir=tmp_path,
                             samples_per_bucket=5, readme_sample=4, seed=7, log=lambda m: None)

    assert report["pool"]["stars>=100"] == 30
    # 100..199 구간 5개 + mock 이 범위 질의를 계산해 잡히는 mcp-files(1000..1999) · agent-kit(20000..49999)
    assert report["sample"]["n"] == 7
    assert report["trending"]["rows"] == 2
    assert report["trending"]["coverage"]["1000"] == 1.0
    assert report["readme"]["n"] + report["readme"]["missing"] == 4  # README 없는 저장소는 missing 으로 센다
    assert report["week_boundary"]["utc_offset_hours"] == [0.0]
    assert report["week_boundary"]["current_week_present"] is True
    assert (tmp_path / "report.json").exists() and (tmp_path / "samples.jsonl").exists()


def test_probe_report_never_has_naive_datetimes():
    # 보고서의 날짜는 모두 ISO 문자열이어야 JSON 으로 남는다
    assert probe.iso(datetime(2026, 10, 26, tzinfo=UTC)) == "2026-10-26T00:00:00+00:00"
