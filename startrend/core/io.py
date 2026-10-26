"""파일 입출력. 인코딩을 항상 명시하고, 줄바꿈은 LF 로 고정한다.

윈도우와 맥북을 오가며 작업하므로 줄바꿈이 섞이면 같은 내용의 해시가 달라진다.
쓰기는 임시 파일 → os.replace 로 원자적이다. 중간에 죽어도 반쯤 쓴 정본 파일이 남지 않는다.
"""

import json
import os
import tempfile
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

_BOM = b"\xef\xbb\xbf"


class ImmutableFileError(Exception):
    """한 번 쓴 주간 파일을 다른 내용으로 덮으려 했다 (SPEC NFR-5 ②)."""


def read_text(path: Path) -> str:
    """utf-8 → (BOM 이면 utf-8-sig) → cp949 순으로 읽는다."""
    raw = path.read_bytes()
    if raw.startswith(_BOM):
        return raw[len(_BOM):].decode("utf-8")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp949")


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_immutable(path: Path, text: str) -> bool:
    """처음이면 쓰고 True. 같은 내용이 이미 있으면 False. 다른 내용이면 ImmutableFileError."""
    if path.exists():
        if read_text(path) == text:
            return False
        raise ImmutableFileError(f"이미 쓴 파일은 다시 쓰지 않는다: {path}")
    write_text_atomic(path, text)
    return True


def write_if_changed(path: Path, text: str) -> bool:
    """내용이 바뀔 때만 쓴다 (SPEC NFR-5 ①). 썼으면 True."""
    if path.exists() and read_text(path) == text:
        return False
    write_text_atomic(path, text)
    return True


def dumps_json(obj: Any) -> str:
    """결정론적 JSON — 키 정렬, 한글 그대로, 끝 줄바꿈."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def write_json(path: Path, obj: Any) -> None:
    write_text_atomic(path, dumps_json(obj))


def read_json(path: Path) -> Any:
    return json.loads(read_text(path))


def write_jsonl(path: Path, rows: Iterable[Any]) -> None:
    text = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)
    write_text_atomic(path, text)


def read_jsonl(path: Path) -> Iterator[Any]:
    for line in read_text(path).splitlines():
        if line.strip():
            yield json.loads(line)
