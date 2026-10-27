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


def test_cli_classify_defaults_to_dry_run_without_token(tmp_path, capsys):
    import json

    from startrend.core import io as cio
    from startrend.core import weekfile
    from startrend.core.weekfile import WeekRow

    w = date(2026, 10, 18)
    env = {"STARTREND_DATA_DIR": str(tmp_path / "d"), "STARTREND_WORK_DIR": str(tmp_path / "w")}
    rows = [WeekRow(i, f"o/r{i}", date(2024, 1, 1), 5000 + i, 100 + i, False, None) for i in range(1, 9)]
    weekfile.write(weekfile.week_path(tmp_path / "d", w), rows)
    cio.write_json(tmp_path / "d" / "weekly" / "2026-10-18" / "rankings.json",
                   {"week": "2026-10-18", "pool": {"gain": list(range(8, 0, -1))}})
    assert main(["classify", "--week", w.isoformat()], env=env) == 0   # 토큰 없이 — 호출 0
    out = json.loads(capsys.readouterr().out)
    assert out["first_round"] == 8 and out["upper_bound"] == 8   # 저장소 8개뿐 — 15개 기준이면 전부
    assert out["dry_run"] is True


def test_cli_classify_run_is_not_open_yet(tmp_path, capsys):
    env = {"STARTREND_DATA_DIR": str(tmp_path / "d"), "STARTREND_WORK_DIR": str(tmp_path / "w")}
    assert main(["classify", "--run", "--week", "2026-10-18"], env=env) == 2
    assert "P2-2" in capsys.readouterr().err


# --- eval · goldset-draft (P2-11·P2-12) ---


def _dirs(tmp_path, **extra: str) -> dict[str, str]:
    return {"STARTREND_DATA_DIR": str(tmp_path / "d"), "STARTREND_WORK_DIR": str(tmp_path / "w"), **extra}


def _gold(tmp_path):
    from startrend.core import io as cio

    p = tmp_path / "gold.jsonl"
    cio.write_jsonl(p, [{"repo_id": 1, "full_name": "o/r1", "is_ai": "yes", "type": "도구/라이브러리",
                         "category": "RAG·검색"},
                        {"repo_id": 2, "full_name": "o/r2", "is_ai": "no", "type": "교육자료",
                         "category": None}])
    return p


def test_cli_eval_without_predictions_is_a_dry_run(tmp_path, capsys):
    import json

    assert main(["eval", "--gold", str(_gold(tmp_path))], env=_dirs(tmp_path)) == 0   # 키 없이 — 호출 0
    out = json.loads(capsys.readouterr().out)
    assert out["dry_run"] is True and out["calls"] == 2 and out["usd"][0] > 0


def test_cli_eval_scores_predictions_and_keeps_a_run(tmp_path, capsys):
    import json

    from startrend.core import io as cio

    preds = tmp_path / "pred.jsonl"
    cio.write_jsonl(preds, [{"repo_id": 1, "status": "ok", "is_ai": True, "type": "도구/라이브러리",
                             "category": "rag"},
                            {"repo_id": 2, "status": "ok", "is_ai": True, "type": "교육자료",
                             "category": "rag"}])
    argv = ["eval", "--gold", str(_gold(tmp_path)), "--predictions", str(preds), "--name", "t"]
    assert main(argv, env=_dirs(tmp_path)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["is_ai_accuracy"] == 0.5 and out["category_accuracy"] == 1.0
    runs = list((tmp_path / "d" / "eval" / "runs").glob("*-t.json"))
    assert len(runs) == 1 and runs[0].with_suffix(".md").exists()


def test_cli_goldset_draft_defaults_to_dry_run_without_keys(tmp_path, capsys):
    import json

    from startrend.core import io as cio

    cio.write_jsonl(tmp_path / "d" / "eval" / "goldset_candidates.jsonl",
                    [{"repo_id": i, "full_name": f"o/r{i}", "blind": i == 1} for i in range(1, 5)])
    assert main(["goldset-draft"], env=_dirs(tmp_path)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dry_run"] is True and out["calls"] == 4 and out["github_calls"] == 8 and out["cap_usd"] == 3.0


def test_cli_goldset_draft_run_needs_the_project_anthropic_key(tmp_path, capsys):
    from startrend.core import io as cio

    cio.write_jsonl(tmp_path / "d" / "eval" / "goldset_candidates.jsonl",
                    [{"repo_id": 1, "full_name": "o/r1", "blind": False}])
    env = _dirs(tmp_path, GITHUB_TOKEN="ghp_x", ANTHROPIC_API_KEY="sk-ant-other")
    assert main(["goldset-draft", "--run"], env=env) == 2
    assert "STARTREND_ANTHROPIC_API_KEY" in capsys.readouterr().err
