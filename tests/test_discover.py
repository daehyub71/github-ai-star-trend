"""stages.discover — 후보 발굴 (FR-1, 결정 27). Search 1,000건 상한을 스타 구간 분할로 피한다."""

from datetime import date

import pytest

from startrend.clients.github_mock import MockGitHub
from startrend.core import snapshot
from startrend.stages import discover as dc
from tests import synth

TODAY = date(2026, 10, 26)


def _mock(stars_list: list[int], created_new: set[int] | None = None) -> MockGitHub:
    gh = MockGitHub()
    for i, s in enumerate(stars_list):
        created = "2026-10-20T00:00:00Z" if created_new and i in created_new else "2023-01-01T00:00:00Z"
        gh.add_repo(synth.repo(f"synth/r{i}", id=i + 1, stars=s, created=created))
    return gh


def test_discover_plan_slices_each_under_cap():
    gh = _mock([1000 + i for i in range(57)])  # 1000~1056
    slices = dc.plan_slices(gh, lo=1000, cap=10)
    assert all(s.total <= 10 for s in slices)
    assert sum(s.total for s in slices) == 57
    # 구간이 겹치지 않고 빈틈 없이 이어진다
    for a, b in zip(slices, slices[1:], strict=False):
        assert b.lo == a.hi + 1


def test_discover_plan_slices_open_upper_bound_uses_max():
    gh = _mock([1000, 1200, 90000])
    slices = dc.plan_slices(gh, lo=1000, cap=10)
    assert slices[-1].hi == 90000
    assert sum(s.total for s in slices) == 3


def test_discover_plan_slices_single_dense_value_is_flagged():
    gh = _mock([1000] * 12)  # 스타 값 하나에 12개 — 나눌 수 없다
    slices = dc.plan_slices(gh, lo=1000, cap=10)
    assert len(slices) == 1 and slices[0].dense is True


def test_discover_plan_slices_empty_pool():
    assert dc.plan_slices(_mock([5, 6]), lo=1000, cap=10) == []


def test_discover_query_with_extra_qualifier():
    assert dc.slice_query(dc.Slice(10, 20, 3), " created:>=2026-09-26") == "stars:10..20 created:>=2026-09-26"


def test_discover_enumerate_collects_every_repo_once():
    gh = _mock([1000 + i for i in range(57)])
    slices = dc.plan_slices(gh, lo=1000, cap=10)
    repos, stats = dc.enumerate_slices(gh, slices)
    assert len(repos) == 57 == len({r.id for r in repos})
    summary = {k: stats[k] for k in ("slices", "expected", "found", "dense_slices")}
    assert summary == {"slices": len(slices), "expected": 57, "found": 57, "dense_slices": 0}
    assert stats["gaps"] == [] and stats["incomplete_retries"] == 0


# --- 회귀: 2026-10-26 첫 실제 실행에서 641개 누락 ---


class FlakySearch(MockGitHub):
    """실제 Search 에서 본 세 가지 현상을 흉내 낸다.

    - short: 그 질의의 그 쪽에서 항목 하나를 뺀다 (99개만 온 쪽)
    - incomplete: 그 질의의 그 쪽을 처음 한 번은 incomplete_results=true 로 반쯤만 준다
    - shuffle: 그 질의는 쪽을 넘길 때마다 순서가 흔들려 쪽 경계에서 중복·누락이 생긴다
    """

    def __init__(self, short=(), incomplete=(), shuffle=()):
        super().__init__()
        self.short, self.incomplete, self.shuffle = set(short), set(incomplete), set(shuffle)
        self.seen_incomplete: set[tuple[str, int]] = set()

    def search_repositories(self, query, *, page=1, per_page=100, sort="stars", order="desc"):
        res = super().search_repositories(query, page=page, per_page=per_page, sort=sort, order=order)
        items = list(res.items)
        key = (query, page)
        if key in self.short:
            items = items[:-1]
        if key in self.incomplete and key not in self.seen_incomplete:
            self.seen_incomplete.add(key)
            from startrend.core.models import SearchPage
            return SearchPage(res.total_count, True, tuple(items[: len(items) // 2]))
        if query in self.shuffle and page > 1 and items:
            items = items[1:] + items[:1]  # 앞 쪽의 마지막 항목이 다시 나오고 하나가 빠지는 식
            prev = super().search_repositories(query, page=page - 1, per_page=per_page).items
            items[0] = prev[-1]
        from startrend.core.models import SearchPage
        return SearchPage(res.total_count, res.incomplete_results, tuple(items))


def _flaky(n: int, **kw) -> FlakySearch:
    gh = FlakySearch(**kw)
    for i in range(n):
        gh.add_repo(synth.repo(f"synth/r{i}", id=i + 1, stars=2000 + i))
    return gh


def test_discover_short_page_does_not_stop_enumeration():
    gh = _flaky(250, short={("stars:2000..2249", 1)})
    slices = [dc.Slice(2000, 2249, 250)]
    repos, stats = dc.enumerate_slices(gh, slices, cap=1000)
    assert stats["found"] >= 249  # 예전에는 1쪽(99개)에서 멈췄다


def test_discover_incomplete_page_is_retried_once():
    gh = _flaky(250, incomplete={("stars:2000..2249", 2)})
    repos, stats = dc.enumerate_slices(gh, [dc.Slice(2000, 2249, 250)], cap=1000)
    assert stats["found"] == 250
    assert stats["incomplete_retries"] == 1


def test_discover_repair_pass_recovers_unstable_pagination():
    gh = _flaky(250, shuffle={"stars:2000..2249"})
    slices = [dc.Slice(2000, 2249, 250)]
    repos, stats = dc.enumerate_slices(gh, slices, cap=1000)
    assert stats["found"] < 250  # 흔들린 쪽 경계에서 빠진다
    repaired, rstats = dc.repair(gh, slices, repos, cap=1000, small=100, min_gap=1)
    assert len(repaired) == 250
    assert rstats["repaired_slices"] == 1 and rstats["recovered"] == 250 - stats["found"]


def test_discover_records_gap_per_slice():
    gh = _flaky(250, shuffle={"stars:2000..2249"})
    repos, stats = dc.enumerate_slices(gh, [dc.Slice(2000, 2249, 250)], cap=1000)
    assert stats["gaps"] == [{"query": "stars:2000..2249", "expected": 250, "found": stats["found"]}]


def test_discover_combines_pool_new_and_tracked():
    stars = [5, 15, 1000, 2000, 300]
    gh = _mock(stars, created_new={1})  # r1: 15 스타, 새 저장소
    result = dc.discover(gh, today=TODAY, pool_min=1000, new_days=30, new_min=10,
                         tracked=["synth/r4"], cap=10, log=lambda m: None)
    by_name = {r.full_name: r for r in result.rows}
    assert set(by_name) == {"synth/r1", "synth/r2", "synth/r3", "synth/r4"}
    assert by_name["synth/r1"].sources == ("new",)
    assert by_name["synth/r2"].sources == ("pool",)
    assert by_name["synth/r4"].sources == ("tracked",)
    assert result.stats["pool"]["found"] == 2
    assert result.stats["pool"]["repair"] == {"repaired_slices": 0, "recovered": 0}
    assert result.stats["new"]["found"] == 1
    assert result.stats["tracked"] == {"requested": 1, "found": 1, "missing": []}


def test_discover_repo_in_pool_and_new_has_both_sources():
    gh = _mock([1500], created_new={0})
    result = dc.discover(gh, today=TODAY, cap=10, log=lambda m: None)
    assert result.rows[0].sources == ("pool", "new")


def test_discover_tracked_missing_repo_is_reported():
    gh = _mock([1500])
    result = dc.discover(gh, today=TODAY, tracked=["gone/away"], cap=10, log=lambda m: None)
    assert result.stats["tracked"]["missing"] == ["gone/away"]


def test_discover_snapshot_csv_round_trip(tmp_path):
    gh = _mock([1000, 1500, 2000])
    result = dc.discover(gh, today=TODAY, cap=10, log=lambda m: None)
    path = tmp_path / "2026-10-18.csv"
    snapshot.write(path, result.rows)
    text = path.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "id,full_name,stars,forks,open_issues,created,sources"
    back = snapshot.read(path)
    assert back == {r.id: r for r in result.rows}


def test_discover_snapshot_is_sorted_by_id(tmp_path):
    gh = _mock([2000, 1000, 1500])
    rows = dc.discover(gh, today=TODAY, cap=10, log=lambda m: None).rows
    path = tmp_path / "s.csv"
    snapshot.write(path, list(reversed(rows)))
    ids = [line.split(",")[0] for line in path.read_text(encoding="utf-8").splitlines()[1:]]
    assert ids == sorted(ids, key=int)


@pytest.mark.parametrize("bad", ["a,b", "x"])
def test_discover_read_snapshot_rejects_bad_header(tmp_path, bad):
    p = tmp_path / "bad.csv"
    p.write_text(bad + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        snapshot.read(p)
