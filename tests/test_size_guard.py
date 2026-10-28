"""NFR-5 ⑤ · NFR-14 ③ — 크기 가드. 순수 판정 함수 + 격리된 임시 git 저장소 통합 테스트."""

import subprocess
from pathlib import Path

import pytest

from scripts import size_guard as sg
from startrend.core.config import PROJECT_ROOT

MB = 1_048_576


def test_size_guard_passes_small_files():
    entries = [sg.Entry("startrend/x.py", 0, 2_000), sg.Entry("data/stars/2026/2026-10-25.csv", 0, 600_000)]
    assert sg.check(entries) == []


def test_size_guard_rejects_file_over_1mb():
    v = sg.check([sg.Entry("data/big.json", 0, MB + 1)])
    assert len(v) == 1 and "data/big.json" in v[0] and "1MB" in v[0]


def test_size_guard_exactly_1mb_is_allowed():
    assert sg.check([sg.Entry("data/x.json", 0, MB)]) == []


def test_size_guard_star_file_allows_up_to_2mb():
    # 결정 48: 주간 스타 파일은 증가 ≥ 10 행을 모두 둔다 — 최근 주 1.2~1.3MB(MEASURE §14)라 한도 2MB
    assert sg.check([sg.Entry("data/stars/2026/2026-10-18.csv", 0, 2 * MB)]) == []


def test_size_guard_star_file_rejects_over_2mb():
    v = sg.check([sg.Entry("data/stars/2026/2026-10-18.csv", 0, 2 * MB + 1)])
    assert len(v) == 1 and "data/stars/2026/2026-10-18.csv" in v[0] and "2MB" in v[0]


def test_size_guard_star_limit_is_only_for_star_csv():
    # 같은 크기라도 주간 스타 CSV 가 아니면 1MB 규칙 그대로
    entries = [
        sg.Entry("data/weekly/2026-10-18/rankings.json", 0, MB + 1),
        sg.Entry("data/stars/2026/notes.json", 0, MB + 1),
        sg.Entry("docs/stars/2026/2026-10-18.csv", 0, MB + 1),
    ]
    assert len(sg.check(entries)) == 3


def test_size_guard_rejects_large_data_growth():
    entries = [sg.Entry(f"data/repos/{i}.json", 0, 600_000) for i in range(10)]  # 합계 약 5.7MB
    v = sg.check(entries, max_data_growth=5 * MB)
    assert len(v) == 1 and "data/" in v[0]


def test_size_guard_growth_counts_only_data_dir():
    entries = [sg.Entry(f"docs/img/{i}.png", 0, 900_000) for i in range(10)]
    assert sg.check(entries, max_data_growth=5 * MB) == []


def test_size_guard_growth_uses_delta_not_total():
    # 이미 있던 파일을 조금 고친 것은 증가량이 작다
    entries = [sg.Entry(f"data/repos/{i}.json", 590_000, 600_000) for i in range(10)]
    assert sg.check(entries, max_data_growth=5 * MB) == []


@pytest.mark.parametrize("path", [
    "data/repos/ab/o__r/card.md",
    "data/weekly/2026-10-18/briefing.md",
    "data/cards/o__r.md",
])
def test_size_guard_keeps_llm_cards_out_of_the_public_repo(path):
    # 결정 53: 사람이 검토하지 않은 LLM 카드·브리핑은 공개 저장소에 커밋하지 않는다 — 코드가 막는다
    v = sg.check([sg.Entry(path, 0, 100)])
    assert len(v) == 1 and "결정 53" in v[0]


def test_size_guard_allows_public_data_next_to_cards():
    ok = ["data/repos/ab/o__r/meta.json", "data/weekly/2026-10-18/rankings.json", "docs/cards-design.md"]
    assert sg.check([sg.Entry(p, 0, 100) for p in ok]) == []


def test_size_guard_rejects_non_ascii_filename():
    # 루트 규칙: 리포 파일명은 ASCII 만 (NFD/NFC 차이로 Vercel 배포 실패 사례)
    v = sg.check([sg.Entry("data/한글.json", 0, 10)])
    assert len(v) == 1 and "ASCII" in v[0]


# --- 임시 git 저장소 (사용자 전역 설정과 격리) ---


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return r.stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    # 사용자 전역 git 설정(서명·훅 경로 등)을 읽지 않는다 — 빈 설정 파일로 격리
    empty = tmp_path / "empty.gitconfig"
    empty.write_text("", encoding="utf-8")
    for k, v in {
        "GIT_CONFIG_GLOBAL": str(empty),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    }.items():
        monkeypatch.setenv(k, v)
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    return root


def test_size_guard_staged_entries_new_and_modified(repo):
    (repo / "data").mkdir()
    (repo / "data" / "a.json").write_bytes(b"x" * 100)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")
    (repo / "data" / "a.json").write_bytes(b"x" * 300)
    (repo / "data" / "b.json").write_bytes(b"y" * 50)
    _git(repo, "add", ".")
    entries = {e.path: e for e in sg.staged_entries(repo)}
    assert entries["data/a.json"] == sg.Entry("data/a.json", 100, 300)
    assert entries["data/b.json"] == sg.Entry("data/b.json", 0, 50)


def test_size_guard_staged_entries_before_first_commit(repo):
    (repo / "x.txt").write_bytes(b"abc")
    _git(repo, "add", ".")
    assert sg.staged_entries(repo) == [sg.Entry("x.txt", 0, 3)]


def test_size_guard_main_fails_on_big_staged_file(repo, capsys):
    (repo / "data").mkdir()
    (repo / "data" / "big.bin").write_bytes(b"0" * (MB + 10))
    _git(repo, "add", ".")
    assert sg.main(["--staged", "--repo", str(repo)]) == 1
    assert "data/big.bin" in capsys.readouterr().err


def test_size_guard_main_passes_clean_stage(repo):
    (repo / "ok.txt").write_bytes(b"ok")
    _git(repo, "add", ".")
    assert sg.main(["--staged", "--repo", str(repo)]) == 0


def test_size_guard_pre_commit_hook_runs_full_gate():
    hook = (PROJECT_ROOT / "scripts" / "hooks" / "pre-commit").read_text(encoding="utf-8")
    for cmd in ("ruff check", "mypy", "pytest", "size_guard.py --staged"):
        assert cmd in hook, cmd


def test_measure_web_search_cost_formula():
    # scripts/measure_web_search.py — Opus 5.5 단가(MEASURE §9)와 검색 1회 $0.01
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "measure_web_search", Path(__file__).resolve().parents[1] / "scripts" / "measure_web_search.py")
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    c = m.cost({"input_tokens": 1_000_000, "output_tokens": 100_000, "web_search_requests": 3})
    assert round(c, 4) == round(4.0 + 2.0 + 0.03, 4)
