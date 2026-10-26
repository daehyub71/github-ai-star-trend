"""저장소 메타 `data/repos/<하위폴더>/<owner>__<repo>/meta.json` (PLAN 1-5, SPEC NFR-5 ①·④).

- 랭킹에 든 저장소만 둔다. 천천히 바뀌는 값(설명·토픽·언어·생성일·처음/마지막 등장 주)만 담는다 —
  매주 바뀌는 값(스타·포크·이슈)은 주간 파일과 랭킹 파일에 둔다.
- 정체성은 숫자 ID. 하위 폴더는 ID 해시 앞 2자리(256개) — 이름이 바뀌어도 하위 폴더는 그대로다.
- 이름이 바뀌면 폴더(카드 포함)를 새 이름으로 옮기고 이전 이름을 aliases 에 남긴다.
- 내용이 바뀔 때만 다시 쓴다.
"""

import hashlib
import os
from pathlib import Path
from typing import Any

from startrend.core import io


def shard(repo_id: int) -> str:
    return hashlib.sha256(str(repo_id).encode()).hexdigest()[:2]


def meta_path(data_dir: Path, repo_id: int, full_name: str) -> Path:
    owner, _, name = full_name.partition("/")
    return data_dir / "repos" / shard(repo_id) / f"{owner}__{name}" / "meta.json"


def _find(data_dir: Path, repo_id: int) -> Path | None:
    base = data_dir / "repos" / shard(repo_id)
    if not base.exists():
        return None
    for p in sorted(base.glob("*/meta.json")):
        if io.read_json(p).get("id") == repo_id:
            return p
    return None


def load(data_dir: Path, repo_id: int) -> dict[str, Any] | None:
    p = _find(data_dir, repo_id)
    return dict(io.read_json(p)) if p else None


def save(data_dir: Path, m: dict[str, Any]) -> bool:
    """메타를 저장한다. 바뀐 것이 없으면 False."""
    repo_id, full_name = int(m["id"]), str(m["full_name"])
    target = meta_path(data_dir, repo_id, full_name)
    found = _find(data_dir, repo_id)
    merged = dict(m)
    if found is not None:
        existing = io.read_json(found)
        merged = {**existing, **m}
        if found != target:  # 이름이 바뀌었다
            aliases = list(existing.get("aliases") or [])
            if existing["full_name"] not in aliases:
                aliases.append(existing["full_name"])
            merged["aliases"] = aliases
            target.parent.parent.mkdir(parents=True, exist_ok=True)
            os.replace(found.parent, target.parent)
    return io.write_if_changed(target, io.dumps_json(merged))
