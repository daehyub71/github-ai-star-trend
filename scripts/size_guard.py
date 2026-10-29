"""크기 가드 — 커밋 전 훅이 부른다 (SPEC NFR-5 ⑤ · NFR-14 ③).

막는 것:
- 1MB 를 넘는 파일 (GitHub 권장 상한. 원본 근거를 실수로 커밋하는 것을 막는다)
  — 주간 스타 파일(data/stars/**.csv)만 2MB (결정 48: 최근 주 1.2~1.3MB, MEASURE §14)
- 한 커밋에 data/ 가 5MB 넘게 늘어나는 것 (주간 실행 한 번은 약 1.5MB)
- ASCII 가 아닌 파일명 (루트 규칙: NFD/NFC 차이로 Vercel 배포 실패 사례)
- data/ 아래 LLM 카드·브리핑 (결정 53: 사람이 검토하지 않은 LLM 글은 공개 저장소에 커밋하지 않는다)
- 시크릿 (P5-6 F3: 무인 실행이 data/ 를 공개 저장소에 커밋한다) — 토큰 모양과 환경변수의 실제 키 값.
  규칙은 startrend.core.secrets(압축본과 같은 규칙). 보고에 값은 쓰지 않는다

    .\\.venv\\Scripts\\python.exe scripts\\size_guard.py --staged
"""

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# `python scripts/size_guard.py` 로 불려도 startrend 를 찾게
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from startrend.core.secrets import scan_text, secret_values  # noqa: E402

MB = 1_048_576
MAX_FILE = MB
MAX_STAR_FILE = 2 * MB  # 결정 48 — 증가 ≥ 10 행을 모두 두는 주간 스타 파일
MAX_DATA_GROWTH = 5 * MB  # 주간 실행 한 번(스타 파일 + 랭킹 + 메타)은 약 1.5MB — MEASURE §14
_LLM_TEXT = re.compile(r"^data/(?:.+/)?(?:card|briefing)\.md$|^data/cards/")   # 결정 53
_PHASE_4B = re.compile(r"^data/(?:blog|notion)/")   # 결정 59 — 블로그 초안·사진·Notion 대응표


@dataclass(frozen=True)
class Entry:
    path: str  # 저장소 기준 POSIX 경로
    old_size: int  # HEAD 의 크기. 새 파일이면 0
    new_size: int  # 스테이징된 크기


def check(entries: list[Entry], max_file: int = MAX_FILE,
          max_data_growth: int = MAX_DATA_GROWTH, max_star_file: int = MAX_STAR_FILE) -> list[str]:
    violations = []
    for e in entries:
        if not e.path.isascii():
            violations.append(f"{e.path}: 파일명은 ASCII 만 쓴다")
        if _LLM_TEXT.match(e.path):
            violations.append(f"{e.path}: LLM 카드·브리핑은 공개 저장소에 커밋하지 않는다 (결정 53)")
        if _PHASE_4B.match(e.path):
            violations.append(f"{e.path}: 블로그·Notion 내용은 공개 저장소에 올리지 않는다 (결정 59)")
        limit = max_star_file if _is_star_file(e.path) else max_file
        if e.new_size > limit:
            violations.append(
                f"{e.path}: {e.new_size / MB:.2f}MB — {limit / MB:g}MB 를 넘는 파일은 커밋하지 않는다"
            )
    growth = sum(e.new_size - e.old_size for e in entries if e.path.startswith("data/"))
    if growth > max_data_growth:
        violations.append(
            f"data/ 가 이번 커밋에서 {growth / MB:.2f}MB 늘어난다 — 기준 {max_data_growth / MB:.0f}MB 초과"
        )
    return violations


def _is_star_file(path: str) -> bool:
    return path.startswith("data/stars/") and path.endswith(".csv")


def staged_entries(repo: Path) -> list[Entry]:
    out = _git(repo, "diff", "--cached", "--name-only", "--no-renames", "--diff-filter=AM", "-z")
    paths = [p for p in out.split("\0") if p]
    if not paths:
        return []
    has_head = subprocess.run(
        ["git", "rev-parse", "--verify", "-q", "HEAD"], cwd=repo, capture_output=True
    ).returncode == 0
    new = _sizes(repo, [f":{p}" for p in paths])
    old = _sizes(repo, [f"HEAD:{p}" for p in paths]) if has_head else [0] * len(paths)
    return [Entry(p, o, n) for p, o, n in zip(paths, old, new, strict=True)]


BINARY = (".webp", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".gz", ".zip", ".pdf", ".woff", ".woff2")


def staged_secret_hits(repo: Path, paths: list[str], secrets: list[str]) -> list[str]:
    """스테이징된 내용(작업 트리가 아니라 인덱스)에서 시크릿을 찾는다 — "파일:줄 (종류)"만."""
    hits: list[str] = []
    for p in paths:
        if p.lower().endswith(BINARY):
            continue
        blob = subprocess.run(["git", "show", f":{p}"], cwd=repo, capture_output=True, check=True).stdout
        for no, line in enumerate(blob.decode("utf-8", errors="ignore").splitlines(), 1):
            for kind in scan_text(line, secrets=secrets):
                hits.append(f"{p}:{no} ({kind})")
    return hits


def _sizes(repo: Path, objects: list[str]) -> list[int]:
    out = _git(repo, "cat-file", "--batch-check=%(objectsize)", stdin="\n".join(objects) + "\n")
    return [0 if line.endswith(" missing") else int(line) for line in out.splitlines()]


def _git(repo: Path, *args: str, stdin: str | None = None) -> str:
    r = subprocess.run(
        ["git", *args], cwd=repo, input=stdin, capture_output=True, text=True, encoding="utf-8", check=True
    )
    return r.stdout


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="size_guard")
    ap.add_argument("--staged", action="store_true", help="스테이징된 변경을 검사한다 (커밋 전 훅)")
    ap.add_argument("--repo", default=".", help="git 저장소 경로")
    ap.add_argument("--max-data-growth-mb", type=float, default=MAX_DATA_GROWTH / MB)
    args = ap.parse_args(argv)
    if not args.staged:
        ap.error("지금은 --staged 만 지원한다")
    repo = Path(args.repo)
    entries = staged_entries(repo)
    violations = check(entries, max_data_growth=int(args.max_data_growth_mb * MB))
    for hit in staged_secret_hits(repo, [e.path for e in entries], secret_values(os.environ)):
        violations.append(f"{hit}: 시크릿으로 보인다 — 커밋하지 않는다")
    for v in violations:
        print(f"[size_guard] {v}", file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
