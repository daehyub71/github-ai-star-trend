"""비공개 저장소 ↔ 작업 폴더 동기화 (SPEC FR-11.8, 결정 53·55) — 파일 복사만, git 은 워크플로가 한다.

Actions 는 실행마다 작업 폴더가 새로 생긴다. 다음 주 '다시 등장'에 쓸 최신 카드 보관소와 주별 카드·브리핑,
사이트용 비공개 사본은 비공개 저장소에 둔다.
근거 원문·캐시·스냅샷은 옮기지 않는다(원문은 압축본, 스냅샷은 공개 Release).

    비공개 저장소              작업 폴더(.work)
    cards/                 ↔  cards/
    site-private/          ↔  site-private/
    weeks/<주>/briefing.md ↔  <주>/briefing.md
    weeks/<주>/cards/      ↔  <주>/cards/

한쪽에만 있는 파일은 지우지 않는다(사용자 데이터 원칙). 같은 파일은 새 내용으로 덮는다.
"""

import re
import shutil
from pathlib import Path
from typing import Any

WEEK = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TREES = ("cards", "site-private")


def _copy_tree(src: Path, dst: Path) -> int:
    if not src.is_dir():
        return 0
    n = 0
    for f in sorted(src.rglob("*")):
        if f.is_file():
            target = dst / f.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, target)
            n += 1
    return n


def _copy_file(src: Path, dst: Path) -> int:
    if not src.is_file():
        return 0
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return 1


def push(work_dir: Path, private_dir: Path) -> dict[str, Any]:
    """작업 폴더 → 비공개 저장소 체크아웃."""
    n = sum(_copy_tree(work_dir / t, private_dir / t) for t in TREES)
    weeks = sorted(d.name for d in work_dir.iterdir() if d.is_dir() and WEEK.match(d.name)) \
        if work_dir.exists() else []
    for w in weeks:
        n += _copy_file(work_dir / w / "briefing.md", private_dir / "weeks" / w / "briefing.md")
        n += _copy_tree(work_dir / w / "cards", private_dir / "weeks" / w / "cards")
    return {"files": n, "weeks": weeks}


def pull(private_dir: Path, work_dir: Path) -> dict[str, Any]:
    """비공개 저장소 체크아웃 → 작업 폴더."""
    n = sum(_copy_tree(private_dir / t, work_dir / t) for t in TREES)
    root = private_dir / "weeks"
    weeks = sorted(d.name for d in root.iterdir() if d.is_dir() and WEEK.match(d.name)) \
        if root.exists() else []
    for w in weeks:
        n += _copy_file(root / w / "briefing.md", work_dir / w / "briefing.md")
        n += _copy_tree(root / w / "cards", work_dir / w / "cards")
    return {"files": n, "weeks": weeks}
