"""stages.evidence — 출처들을 차례로 부르고, 한 출처가 실패해도 멈추지 않는다 (FR-5.6·5.7·5.8).

근거 목록은 `.work/<주>/evidence.jsonl`, 원문은 `.work/<주>/raw/<해시>.txt` (PLAN 1-4).
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from startrend.budget import BudgetExceeded
from startrend.clients.evidence.base import MockSource, SourceError, Target
from startrend.core import evidence as ev
from startrend.core import io
from startrend.stages import evidence as st

W = date(2026, 10, 18)
T = datetime(2026, 10, 28, 5, 0, tzinfo=UTC)
TARGET = Target(1, "o/r", since=date(2026, 10, 18), until=date(2026, 10, 24), focus=(date(2026, 10, 20),))


def _doc(url: str, source: str = "web", text: str = "본문") -> ev.Evidence:
    return ev.make(url=url, source=source, kind="search", title=url, text=text, fetched_at=T)


def test_evidence_mock_source_returns_docs_and_records_asks():
    s = MockSource("hn", {"o/r": [_doc("https://news.ycombinator.com/item?id=1", "hn")]})
    assert [d.url for d in s.collect(TARGET)] == ["https://news.ycombinator.com/item?id=1"]
    assert s.collect(Target(2, "x/y", since=W, until=W)) == []
    assert s.asked == ["o/r", "x/y"]


def test_evidence_gather_merges_sources_in_order_and_dedupes():
    a = MockSource("github", {"o/r": [_doc("https://github.com/o/r/releases/tag/v1", "github")]})
    b = MockSource("web", {"o/r": [_doc("https://e.com/x"), _doc("https://github.com/o/r/releases/tag/v1/")]})
    c = st.gather(TARGET, [a, b], log=lambda m: None)
    assert [d.source for d in c.docs] == ["github", "web"] and c.failures == []


@pytest.mark.parametrize("err", [SourceError("HN 503"), TimeoutError("느림"), ValueError("형식이 다르다")])
def test_evidence_gather_isolates_a_failing_source(err):
    # FR-5.7 — 한 출처가 실패해도 나머지는 모은다. 실패는 카드에 "수집 실패"로 남길 수 있게 기록한다
    bad = MockSource("hn", fail={"o/r": err})
    good = MockSource("web", {"o/r": [_doc("https://e.com/x")]})
    logs: list[str] = []
    c = st.gather(TARGET, [bad, good], log=logs.append)
    assert [d.url for d in c.docs] == ["https://e.com/x"]
    assert c.failures == [{"source": "hn", "error": f"{type(err).__name__}: {err}"}]
    assert c.failed_sources == ["hn"] and any("hn" in m for m in logs)


def test_evidence_gather_does_not_swallow_budget_stop():
    with pytest.raises(BudgetExceeded):
        st.gather(TARGET, [MockSource("web", fail={"o/r": BudgetExceeded("cap")})], log=lambda m: None)


def test_evidence_gather_truncates_long_error_messages():
    c = st.gather(TARGET, [MockSource("web", fail={"o/r": SourceError("x" * 5000)})], log=lambda m: None)
    assert len(c.failures[0]["error"]) <= st.ERROR_CHARS


def test_evidence_write_and_read_round_trip(tmp_path):
    docs = [_doc("https://e.com/x", text="원문 전체 " * 100), _doc("https://e.com/y", text="")]
    c = st.Collected(TARGET, docs, [{"source": "hn", "error": "SourceError: 503"}])
    path = st.write(tmp_path, W, [c])
    assert path == tmp_path / "2026-10-18" / "evidence.jsonl"
    row = next(io.read_jsonl(path))
    assert row["repo_id"] == 1 and row["focus"] == ["2026-10-20"] and "text" not in row["docs"][0]
    raw = tmp_path / "2026-10-18" / "raw" / f"{docs[0].content_hash}.txt"
    assert io.read_text(raw) == docs[0].text
    assert not (tmp_path / "2026-10-18" / "raw" / f"{docs[1].content_hash}.txt").exists()
    back = st.read(tmp_path, W)
    assert back[1].target == TARGET and [d.url for d in back[1].docs] == ["https://e.com/x", "https://e.com/y"]
    assert back[1].failed_sources == ["hn"]


def _week_data(tmp_path) -> None:
    """2026-10-18 주: AI 탭에 o/a(두 축에 겹침)·o/b, 앞 4주 일별 곡선 — o/a 는 10-20 에 급등."""
    from startrend.core import weekfile
    from startrend.core.weekfile import WeekRow

    for k in range(4, 0, -1):
        start = date(2026, 10, 18) - timedelta(days=7 * k)
        weekfile.write(weekfile.week_path(tmp_path, start),
                       [WeekRow(1, "o/a", date(2025, 1, 1), 1000, 70, True, (10,) * 7)])
    weekfile.write(weekfile.week_path(tmp_path, W),
                   [WeekRow(1, "o/a", date(2025, 1, 1), 3000, 2060, True, (10, 10, 2000, 10, 10, 10, 10)),
                    WeekRow(2, "o/b", date(2026, 10, 1), 900, 300, False, None)])
    a = {"id": 1, "full_name": "o/a", "created": "2025-01-01"}
    b = {"id": 2, "full_name": "o/b", "created": "2026-10-01"}
    io.write_json(tmp_path / "weekly" / "2026-10-18" / "rankings.json", {"week": "2026-10-18", "axes": {
        "gain": {"all": [a, b], "ai": [a, b]}, "fresh": {"all": [b], "ai": [b]},
        "growth": {"all": [a], "ai": [a]}, "total": {"all": [a], "ai": None}}})


def test_evidence_targets_are_unique_ai_tab_entries_with_spike_days(tmp_path):
    _week_data(tmp_path)
    ts = st.targets_for(tmp_path, W)
    assert [(t.repo_id, t.full_name) for t in ts] == [(1, "o/a"), (2, "o/b")]
    a, b = ts
    assert (a.since, a.until) == (date(2026, 10, 18), date(2026, 10, 24))
    assert a.focus == (date(2026, 10, 20),)              # 앞 4주 곡선 위의 급등일
    assert b.focus == ()                                 # 정밀 값이 없으면 급등일도 없다


def test_evidence_targets_can_be_narrowed_to_named_repos(tmp_path):
    _week_data(tmp_path)
    assert [t.full_name for t in st.targets_for(tmp_path, W, repos=["O/B", "x/missing"])] == ["o/b"]
    with pytest.raises(FileNotFoundError):
        st.targets_for(tmp_path, date(2026, 10, 11))


def test_evidence_plan_counts_calls_without_making_any(tmp_path):
    _week_data(tmp_path)
    p = st.plan(st.targets_for(tmp_path, W), web_queries=3)
    assert p["targets"] == 2 and p["tavily_credits"] == 6
    assert p["geeknews_requests"] == [7, 21] and p["hn_calls"] == 4
    assert p["github_calls_max"] == 14 and p["cost_usd"] == 0


def test_evidence_run_merges_into_the_week_file(tmp_path):
    work = tmp_path / "w"
    first = st.Collected(Target(1, "o/a", since=W, until=W), [_doc("https://e.com/a")], [])
    st.write(work, W, [first])
    src = MockSource("web", {"o/b": [_doc("https://e.com/b")]})
    stats = st.run_evidence([src], [Target(2, "o/b", since=W, until=W)], work_dir=work, week_start=W,
                            log=lambda m: None)
    assert stats == {"targets": 1, "docs": 1, "by_source": {"web": 1}, "failures": 0}
    assert sorted(st.read(work, W)) == [1, 2]            # 앞서 모은 o/a 는 남는다


def test_evidence_urls_feed_the_gate():
    c = st.Collected(TARGET, [_doc("https://e.com/x"), _doc("https://e.com/y")], [])
    assert c.urls == ["https://e.com/x", "https://e.com/y"]
