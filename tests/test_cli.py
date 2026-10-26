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
