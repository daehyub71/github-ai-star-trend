"""주간 압축본 (SPEC FR-10, 결정 29·55) — 비용 0. 올리기는 워크플로가 GitHub 도구로 한다.

- `evidence-<주>.tar.gz` — 근거 원문(`raw/`) + 근거 목록 + LLM 로그
  (카드 초안·게이트·품질·실행 장부, 주간 장부).
  LLM 이 쓴 글과 외부 글 원문이 들어 있으므로 **비공개 저장소의 Release** 로만 올린다(결정 53·55).
- `snapshot-<주>.csv.gz` — 스타 ≥1,000 전체 스냅샷(공개 데이터) → 공개 저장소 Release(결정 29).

올리기 전 시크릿 검사(FR-10.3): 알려진 토큰 모양과 실제 키 값(환경변수)을 찾는다.
하나라도 걸리면 아무 압축본도 만들지 않는다. 보고에는 파일·줄·종류만 남기고 값은 절대 쓰지 않는다.
"""

import gzip
import io as _bytesio
import tarfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from startrend.core.secrets import scan_text as scan_text  # 규칙은 core 한 곳(크기 가드와 같게)

MAX_BYTES = 2 * 1024**3 - 64 * 1024**2      # GitHub Release 파일 하나 2GiB 아래(FR-10.2) — 여유 64MiB


class SecretFound(RuntimeError):
    """압축본에 시크릿으로 보이는 것이 있다 — 올리지 않는다."""


class ArchiveTooLarge(RuntimeError):
    """압축본이 Release 파일 한도를 넘는다."""


def evidence_files(work_dir: Path, week: str) -> list[Path]:
    base = work_dir / week
    out: list[Path] = []
    if (base / "raw").exists():
        out += [p for p in (base / "raw").rglob("*") if p.is_file()]
    if (base / "evidence.jsonl").exists():
        out.append(base / "evidence.jsonl")
    if (base / "cards").exists():
        out += [p for p in (base / "cards").glob("*.json") if p.is_file()]
    out += [p for p in base.glob("weekly-ledger-*.json") if p.is_file()]
    return sorted(out)


def _scan_files(files: Sequence[Path], root: Path, secrets: Sequence[str]) -> list[str]:
    hits: list[str] = []
    for f in files:
        text = f.read_bytes().decode("utf-8", errors="ignore")
        for no, line in enumerate(text.splitlines(), 1):
            for kind in scan_text(line, secrets=secrets):
                hits.append(f"{f.relative_to(root).as_posix()}:{no} ({kind})")
    return hits


def build(work_dir: Path, week: str, *, secrets: Sequence[str], max_bytes: int = MAX_BYTES) -> dict[str, Any]:
    base = work_dir / week
    files = evidence_files(work_dir, week)
    snap = work_dir / "snapshots" / f"{week}.csv"
    hits = _scan_files(files, base, secrets)
    if snap.exists():
        hits += _scan_files([snap], work_dir, secrets)
    if hits:
        shown = ", ".join(hits[:10]) + (f" 외 {len(hits) - 10}건" if len(hits) > 10 else "")
        raise SecretFound(f"시크릿 의심 {len(hits)}건 — 압축본을 만들지 않는다: {shown}")

    out_dir = work_dir / "archive" / week
    result: dict[str, Any] = {"week": week, "evidence": None, "snapshot": None,
                              "files": len(files), "bytes": 0}
    if files:
        buf = _bytesio.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as t:
            for f in files:
                t.add(f, arcname=f.relative_to(base).as_posix())
        data = buf.getvalue()
        if len(data) > max_bytes:
            raise ArchiveTooLarge(f"evidence-{week}.tar.gz {len(data):,}바이트 — "
                                  f"한도 {max_bytes:,}바이트를 넘는다")
        out_dir.mkdir(parents=True, exist_ok=True)
        ev = out_dir / f"evidence-{week}.tar.gz"
        ev.write_bytes(data)
        result.update(evidence=str(ev), bytes=len(data))
    if snap.exists():
        out_dir.mkdir(parents=True, exist_ok=True)
        gz = out_dir / f"snapshot-{week}.csv.gz"
        gz.write_bytes(gzip.compress(snap.read_bytes(), mtime=0))
        result["snapshot"] = str(gz)
    return result
