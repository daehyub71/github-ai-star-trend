"""크기 가드 — 커밋 전 훅이 부른다 (SPEC NFR-5 ⑤ · NFR-14 ③).

막는 것:
- 1MB 를 넘는 파일 (GitHub 권장 상한. 원본 근거를 실수로 커밋하는 것을 막는다)
  — 주간 스타 파일(data/stars/**.csv)만 2MB (결정 48: 최근 주 1.2~1.3MB, MEASURE §14)
- 한 커밋에 data/ 가 5MB 넘게 늘어나는 것 (주간 실행 한 번은 약 1.5MB)
- ASCII 가 아닌 파일명 (루트 규칙: NFD/NFC 차이로 Vercel 배포 실패 사례)

    .\\.venv\\Scripts\\python.exe scripts\\size_guard.py --staged
"""

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

MB = 1_048_576
MAX_FILE = MB
MAX_STAR_FILE = 2 * MB  # 결정 48 — 증가 ≥ 10 행을 모두 두는 주간 스타 파일
MAX_DATA_GROWTH = 5 * MB  # 주간 실행 한 번(스타 파일 + 랭킹 + 메타)은 약 1.5MB — MEASURE §14


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
    violations = check(staged_entries(Path(args.repo)), max_data_growth=int(args.max_data_growth_mb * MB))
    for v in violations:
        print(f"[size_guard] {v}", file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
