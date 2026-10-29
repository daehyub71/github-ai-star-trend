"""stages.archive — 주간 압축본 (FR-10, 결정 29·55). 비용 0 — 올리기는 워크플로가 한다.

- evidence-<주>.tar.gz: 근거 원문 + 근거 목록 + LLM 로그(카드 초안·게이트·실행 장부).
  비공개 저장소 Release 로 간다.
- snapshot-<주>.csv.gz: 전체 스냅샷(공개 데이터). 공개 저장소 Release 로 간다.
- 올리기 전에 시크릿 패턴과 실제 키 값을 검사한다(FR-10.3). 걸리면 아무 압축본도 만들지 않는다.
"""

import gzip
import tarfile
from pathlib import Path

import pytest

from startrend.stages import archive

W = "2026-10-25"
FAKE_GH = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"       # 형식만 맞춘 가짜 값


def _work(tmp_path: Path) -> Path:
    work = tmp_path / "w"
    (work / W / "raw").mkdir(parents=True)
    (work / W / "raw" / "abc.txt").write_text("README 본문", encoding="utf-8")
    (work / W / "evidence.jsonl").write_text('{"repo_id": 1}\n', encoding="utf-8")
    (work / W / "cards").mkdir()
    (work / W / "cards" / "o__a.draft.json").write_text("{}", encoding="utf-8")
    (work / W / "cards" / "run-2026-11-02.json").write_text('{"ledger": []}', encoding="utf-8")
    (work / W / "weekly-ledger-2026-11-02.json").write_text('{"ledger": []}', encoding="utf-8")
    (work / "cache" / "evidence" / W).mkdir(parents=True)
    (work / "cache" / "evidence" / W / "x.json").write_text("{}", encoding="utf-8")   # 캐시는 넣지 않는다
    (work / "snapshots").mkdir()
    (work / "snapshots" / f"{W}.csv").write_text("id,full_name\n1,o/a\n", encoding="utf-8")
    return work


def test_archive_packs_evidence_and_llm_logs_but_not_caches(tmp_path):
    work = _work(tmp_path)
    out = archive.build(work, W, secrets=[])
    ev = Path(out["evidence"])
    assert ev.name == f"evidence-{W}.tar.gz" and ev.parent == work / "archive" / W
    with tarfile.open(ev) as t:
        names = sorted(t.getnames())
    assert names == ["cards/o__a.draft.json", "cards/run-2026-11-02.json", "evidence.jsonl", "raw/abc.txt",
                     "weekly-ledger-2026-11-02.json"]
    assert out["files"] == 5


def test_archive_compresses_the_snapshot_unchanged(tmp_path):
    work = _work(tmp_path)
    out = archive.build(work, W, secrets=[])
    snap = Path(out["snapshot"])
    assert snap.name == f"snapshot-{W}.csv.gz"
    assert gzip.decompress(snap.read_bytes()) == (work / "snapshots" / f"{W}.csv").read_bytes()


def test_archive_stops_on_a_token_pattern_and_never_prints_it(tmp_path):
    work = _work(tmp_path)
    (work / W / "raw" / "leak.txt").write_text(f"예시 토큰 {FAKE_GH} 입니다", encoding="utf-8")
    with pytest.raises(archive.SecretFound) as e:
        archive.build(work, W, secrets=[])
    msg = str(e.value)
    assert "raw/leak.txt" in msg and "GitHub" in msg and FAKE_GH not in msg
    assert not (work / "archive").exists()                       # 아무 압축본도 만들지 않는다


def test_archive_stops_on_an_exact_key_value_from_the_environment(tmp_path):
    work = _work(tmp_path)
    (work / W / "cards" / "o__a.draft.json").write_text('{"x": "my-own-key-value-123"}', encoding="utf-8")
    with pytest.raises(archive.SecretFound) as e:
        archive.build(work, W, secrets=["my-own-key-value-123", ""])
    assert "my-own-key-value-123" not in str(e.value)


@pytest.mark.parametrize("sample", [
    FAKE_GH,
    "github_pat_" + "1" * 22 + "_" + "a" * 59,
    "sk-ant-api03-" + "x" * 40,
    "tvly-" + "d" * 32,
    "ntn_" + "1" * 46,
    "AKIA" + "ABCDEFGHIJKLMNOP",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
])
def test_archive_secret_scan_catches_each_known_shape(sample):
    # 통제군 — 검사기가 실제로 잡는지
    assert archive.scan_text(f"앞 {sample} 뒤", secrets=[])


def test_archive_secret_scan_passes_ordinary_text():
    assert archive.scan_text("ghp 라는 단어와 sk-ant 설명, 짧은 tvly-abc", secrets=[]) == []


def test_archive_refuses_a_file_over_the_release_limit(tmp_path):
    work = _work(tmp_path)
    with pytest.raises(archive.ArchiveTooLarge):
        archive.build(work, W, secrets=[], max_bytes=10)
