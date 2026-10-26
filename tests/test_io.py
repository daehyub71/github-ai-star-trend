"""core.io — 인코딩 명시·원자적 쓰기·주간 파일 불변 가드 (SPEC NFR-4·5·12)."""

import pytest

from startrend.core import io


def test_io_write_text_uses_lf_and_utf8(tmp_path):
    p = tmp_path / "a.txt"
    io.write_text_atomic(p, "한글\n둘째 줄\n")
    raw = p.read_bytes()
    assert b"\r\n" not in raw  # 윈도우에서도 LF — 맥북과 해시가 같아야 한다
    assert raw.decode("utf-8") == "한글\n둘째 줄\n"


def test_io_write_creates_parent_dirs(tmp_path):
    p = tmp_path / "x" / "y" / "a.txt"
    io.write_text_atomic(p, "ok")
    assert io.read_text(p) == "ok"


def test_io_write_leaves_no_temp_files(tmp_path):
    p = tmp_path / "a.txt"
    io.write_text_atomic(p, "ok")
    assert [f.name for f in tmp_path.iterdir()] == ["a.txt"]


def test_io_read_text_strips_bom(tmp_path):
    p = tmp_path / "bom.txt"
    p.write_bytes("﻿내용".encode())
    assert io.read_text(p) == "내용"


def test_io_read_text_falls_back_to_cp949(tmp_path):
    p = tmp_path / "cp.txt"
    p.write_bytes("한글".encode("cp949"))
    assert io.read_text(p) == "한글"


def test_io_immutable_first_write(tmp_path):
    p = tmp_path / "2026-10-25.csv"
    assert io.write_immutable(p, "a\n") is True
    assert io.read_text(p) == "a\n"


def test_io_immutable_same_content_is_noop(tmp_path):
    # 재실행(원칙 5)에서 같은 내용이면 조용히 넘어간다
    p = tmp_path / "2026-10-25.csv"
    io.write_immutable(p, "a\n")
    assert io.write_immutable(p, "a\n") is False


def test_io_immutable_different_content_raises(tmp_path):
    p = tmp_path / "2026-10-25.csv"
    io.write_immutable(p, "a\n")
    with pytest.raises(io.ImmutableFileError):
        io.write_immutable(p, "b\n")
    assert io.read_text(p) == "a\n"


def test_io_write_if_changed(tmp_path):
    p = tmp_path / "meta.json"
    assert io.write_if_changed(p, "{}\n") is True
    mtime = p.stat().st_mtime_ns
    assert io.write_if_changed(p, "{}\n") is False
    assert p.stat().st_mtime_ns == mtime
    assert io.write_if_changed(p, '{"a": 1}\n') is True


def test_io_json_is_deterministic(tmp_path):
    a = io.dumps_json({"b": 1, "a": "한글"})
    b = io.dumps_json({"a": "한글", "b": 1})
    assert a == b
    assert "한글" in a  # ensure_ascii=False
    assert a.endswith("\n")


def test_io_json_round_trip(tmp_path):
    p = tmp_path / "x.json"
    io.write_json(p, {"k": [1, 2]})
    assert io.read_json(p) == {"k": [1, 2]}


def test_io_jsonl_round_trip(tmp_path):
    p = tmp_path / "x.jsonl"
    rows = [{"a": 1}, {"b": "둘"}]
    io.write_jsonl(p, rows)
    assert list(io.read_jsonl(p)) == rows


def test_io_jsonl_skips_blank_lines(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text('{"a": 1}\n\n{"b": 2}\n', encoding="utf-8")
    assert list(io.read_jsonl(p)) == [{"a": 1}, {"b": 2}]
