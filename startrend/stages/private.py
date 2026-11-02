"""비공개 저장소 ↔ 작업 폴더 동기화 (SPEC FR-11.8, 결정 53·55·66) — 파일 복사만, git 은 워크플로가 한다.

Actions 는 실행마다 작업 폴더가 새로 생긴다. 다음 주 '다시 등장'에 쓸 최신 카드 보관소와 주별 카드·브리핑,
사이트용 비공개 사본은 비공개 저장소에 둔다.
근거 원문·캐시·스냅샷은 옮기지 않는다(원문은 압축본, 스냅샷은 공개 Release).

    비공개 저장소              작업 폴더(.work)
    cards/                 ↔  cards/
    site-private/          ↔  site-private/
    weeks/<주>/briefing.md ↔  <주>/briefing.md
    weeks/<주>/cards/      ↔  <주>/cards/
    notion/index.json      ↔  notion/index.json   (결정 66 — 두 쪽 기록을 합친다)
    weeks/<주>/blog/       ↔  <주>/blog/          (결정 66 — 만든 그림 gen/ 은 빼고)

한쪽에만 있는 파일은 지우지 않는다(사용자 데이터 원칙). 같은 파일은 새 내용으로 덮는다 — 단 두 가지는 예외다.
- Notion 대응표는 자동 실행과 로컬이 함께 쓴다. 덮으면 한쪽이 만든 페이지 기록이 사라져 페이지가 중복으로
  생기므로 키를 합친다. 같은 키의 값이 다르면 받는 쪽 값을 두고 `conflicts` 로 알린다.
- 블로그 파일은 사람이 로컬에서 고친다(그림 결합 · 다시 그리기). 받을(pull) 때는 로컬에 없는 파일만 가져오고,
  내용이 다른 파일은 덮지 않고 `kept_local` 로 알린다. 올릴(push) 때는 덮는다 — 자동 실행은 `keep_blog` 로
  이미 있는 파일을 덮지 않는다(`kept_private`).
"""

import re
import shutil
from pathlib import Path
from typing import Any

from startrend.core import io

WEEK = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TREES = ("cards", "site-private")
NOTION_INDEX = Path("notion") / "index.json"
BLOG_SKIP = {"gen"}            # 사용자가 만든 그림 — 1주 37MB(10-18 실측), 자동 실행에는 필요 없다


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


def _copy_blog(src: Path, dst: Path, *, keep: bool, kept: list[str], label: str) -> int:
    """keep: 받는 쪽에 이미 있는 파일은 덮지 않는다 — 내용이 다르면 kept 에 `label/상대 경로` 로 남긴다."""
    if not src.is_dir():
        return 0
    n = 0
    for f in sorted(src.rglob("*")):
        rel = f.relative_to(src)
        if not f.is_file() or rel.parts[0] in BLOG_SKIP:
            continue
        target = dst / rel
        if keep and target.exists():
            if target.read_bytes() != f.read_bytes():
                kept.append(f"{label}/{rel.as_posix()}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, target)
        n += 1
    return n


def _merge_index(src: Path, dst: Path, conflicts: list[str]) -> int:
    """Notion 대응표를 합친다 — 키 합집합, 같은 키의 값이 다르면 받는 쪽(dst) 값을 둔다."""
    if not src.is_file():
        return 0
    theirs = io.read_json(src)
    if not dst.is_file():
        return _copy_file(src, dst)
    mine = io.read_json(dst)
    merged = dict(mine)
    for key, value in theirs.items():
        cur = merged.get(key)
        if isinstance(value, dict) and isinstance(cur, dict):
            part = dict(cur)
            for k, v in value.items():
                if k not in part:
                    part[k] = v
                elif part[k] != v:
                    conflicts.append(f"{NOTION_INDEX.as_posix()}: {key}.{k}")
            merged[key] = part
        elif cur is None:
            merged[key] = value
        elif cur != value:
            conflicts.append(f"{NOTION_INDEX.as_posix()}: {key}")
    if merged == mine:
        return 0
    io.write_json(dst, merged)
    return 1


def push(work_dir: Path, private_dir: Path, *, keep_blog: bool = False) -> dict[str, Any]:
    """작업 폴더 → 비공개 저장소 체크아웃.

    keep_blog: 비공개 저장소에 이미 있는 블로그 파일은 덮지 않는다 — 자동 실행용. 실행 시작 때 받은
    예전 파일로 그사이 로컬에서 고쳐 올린 것을 되돌리지 않게(결정 66).
    로컬에서 올릴 때는 덮는다(사람이 고친 쪽).
    """
    n = sum(_copy_tree(work_dir / t, private_dir / t) for t in TREES)
    conflicts: list[str] = []
    kept: list[str] = []
    n += _merge_index(work_dir / NOTION_INDEX, private_dir / NOTION_INDEX, conflicts)
    weeks = sorted(d.name for d in work_dir.iterdir() if d.is_dir() and WEEK.match(d.name)) \
        if work_dir.exists() else []
    for w in weeks:
        n += _copy_file(work_dir / w / "briefing.md", private_dir / "weeks" / w / "briefing.md")
        n += _copy_tree(work_dir / w / "cards", private_dir / "weeks" / w / "cards")
        n += _copy_blog(work_dir / w / "blog", private_dir / "weeks" / w / "blog", keep=keep_blog, kept=kept,
                        label=f"{w}/blog")
    return {"files": n, "weeks": weeks, "conflicts": conflicts, "kept_private": kept}


def pull(private_dir: Path, work_dir: Path) -> dict[str, Any]:
    """비공개 저장소 체크아웃 → 작업 폴더."""
    n = sum(_copy_tree(private_dir / t, work_dir / t) for t in TREES)
    conflicts: list[str] = []
    kept: list[str] = []
    n += _merge_index(private_dir / NOTION_INDEX, work_dir / NOTION_INDEX, conflicts)
    root = private_dir / "weeks"
    weeks = sorted(d.name for d in root.iterdir() if d.is_dir() and WEEK.match(d.name)) \
        if root.exists() else []
    for w in weeks:
        n += _copy_file(root / w / "briefing.md", work_dir / w / "briefing.md")
        n += _copy_tree(root / w / "cards", work_dir / w / "cards")
        n += _copy_blog(root / w / "blog", work_dir / w / "blog", keep=True, kept=kept, label=f"{w}/blog")
    return {"files": n, "weeks": weeks, "conflicts": conflicts, "kept_local": kept}
