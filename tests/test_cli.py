"""cli — `python -m startrend <단계>`. 토큰이 없으면 네트워크에 가지 않고 안내 후 종료한다."""

from datetime import date

from startrend.__main__ import main, select_rows
from startrend.core.snapshot import SnapRow


def test_cli_contract_without_token_exits_2(capsys):
    assert main(["contract"], env={}) == 2
    err = capsys.readouterr().err
    assert "GITHUB_TOKEN" in err


def test_cli_probe_without_token_exits_2(capsys):
    assert main(["probe"], env={}) == 2
    assert "GITHUB_TOKEN" in capsys.readouterr().err


def test_cli_discover_without_token_exits_2(capsys):
    assert main(["discover"], env={}) == 2
    assert "GITHUB_TOKEN" in capsys.readouterr().err


def test_cli_requires_subcommand(capsys):
    try:
        main([], env={})
    except SystemExit as e:
        assert e.code == 2
    else:
        raise AssertionError("하위 명령 없이 끝나면 안 된다")


def _env(tmp_path):
    return {"GITHUB_TOKEN": "x", "STARTREND_DATA_DIR": str(tmp_path / "d"),
            "STARTREND_WORK_DIR": str(tmp_path / "w")}


def test_cli_stars_without_snapshot_exits_2(tmp_path, capsys):
    env = _env(tmp_path)
    assert main(["stars", "--week", "2026-10-18"], env=env) == 2
    assert "discover" in capsys.readouterr().err


def test_cli_backfill_without_snapshot_exits_2(tmp_path, capsys):
    env = _env(tmp_path)
    assert main(["backfill", "--weeks", "4"], env=env) == 2


def test_cli_rank_without_week_file_exits_2(tmp_path, capsys):
    env = _env(tmp_path)
    assert main(["rank", "--week", "2026-10-18"], env=env) == 2
    assert "주간 파일이 없다" in capsys.readouterr().err


def _s(rid, stars, src=("pool",)):
    return SnapRow(rid, f"o/r{rid}", stars, 0, 0, date(2026, 1, 1), src)


def test_cli_select_rows_top_and_new_union_sorted_by_id():
    rows = [_s(1, 100), _s(2, 9000), _s(3, 5000), _s(4, 300, ("new",)), _s(5, 800, ("pool", "new"))]
    assert [r.id for r in select_rows(rows, top=2, new=1)] == [2, 3, 5]


def test_cli_select_rows_default_is_all_by_id_with_limit():
    rows = [_s(3, 1), _s(1, 2), _s(2, 3)]
    assert [r.id for r in select_rows(rows)] == [1, 2, 3]
    assert [r.id for r in select_rows(rows, limit=2)] == [1, 2]


def _cache_search(cache_dir, items):
    """CachingTransport 가 남긴 Search 응답 파일을 흉내 낸다."""
    import base64
    import hashlib
    import json

    url = "https://api.github.com/search/repositories?q=stars%3A1000..2000&page=1"
    body = json.dumps({"total_count": len(items), "incomplete_results": False, "items": items}).encode()
    cache_dir.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha256(f"GET {url}".encode()).hexdigest() + ".json"
    (cache_dir / name).write_text(json.dumps({"status": 200, "headers": {}, "url": url,
                                              "body": base64.b64encode(body).decode()}), encoding="utf-8")


def test_cli_goldset_reads_cached_search_without_token(tmp_path):
    import json

    from startrend.core import snapshot
    from tests import synth

    w = date(2026, 10, 18)
    env = {"STARTREND_DATA_DIR": str(tmp_path / "d"), "STARTREND_WORK_DIR": str(tmp_path / "w")}
    rows = [SnapRow(i, f"o/r{i}", 1500 + i, 1, 1, date(2024, 1, 1), ("pool",)) for i in range(1, 6)]
    snapshot.write(tmp_path / "w" / "snapshots" / "2026-10-18.csv", rows)
    items = [synth.repo(f"o/r{i}", id=i, stars=1500 + i, description="LLM tool" if i % 2 else "web server")
             for i in range(1, 6)]
    _cache_search(tmp_path / "w" / "cache" / "2026-10-18", items)
    assert main(["goldset", "--week", w.isoformat()], env=env) == 0  # 토큰 없이 — 네트워크를 쓰지 않는다
    out = tmp_path / "d" / "eval" / "goldset_candidates.jsonl"
    lines = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
    assert sorted(p["repo_id"] for p in lines) == [1, 2, 3, 4, 5]  # 모집단이 200 보다 작으면 전부
    assert {p["signal"] for p in lines} == {"strong", "none"}
