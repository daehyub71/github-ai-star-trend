"""NFR-8 · NFR-14 — Actions 워크플로 보안 규칙을 코드로 검사한다.

통제군: 검사기가 위반을 실제로 잡는지 먼저 본다.

규칙: ① 외부 Action 은 커밋 SHA(40자리)로 고정 ② 권한은 `contents: write` 하나 ③ `pull_request_target` 금지
④ `run:` 스크립트 안에 `${{ … }}` 식 금지 — 시크릿·입력값·단계 출력은 env 로 넘긴다(스크립트 주입 방지)
⑤ 체크아웃은 토큰을 남기지 않는다(`persist-credentials: false`)
⑥ pip 은 해시 고정 잠금 파일로만 설치 (P5-6 F1·F2)
"""

import re

from startrend.core.config import PROJECT_ROOT

USES = re.compile(r"^\s*(?:-\s*)?uses:\s*(\S+)")
PINNED = re.compile(r"^[\w.-]+/[\w.-]+(?:/[\w./-]+)?@[0-9a-f]{40}$")


def run_blocks(text: str) -> list[tuple[int, str]]:
    """(줄 번호, 내용) — `run:` 한 줄짜리와 `run: |` 아래 들여쓴 줄."""
    out: list[tuple[int, str]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^(\s*)(?:-\s*)?run:\s*(.*)$", lines[i])
        if not m:
            i += 1
            continue
        indent, rest = len(m.group(1)), m.group(2)
        if rest and rest not in ("|", ">", "|-", ">-"):
            out.append((i + 1, rest))
            i += 1
            continue
        i += 1
        while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > indent):
            out.append((i + 1, lines[i]))
            i += 1
    return out


def top_permissions(text: str) -> dict[str, str]:
    m = re.search(r"^permissions:[ \t]*(.*)$", text, re.M)
    if not m:
        return {}
    if m.group(1).strip():
        return {"*": m.group(1).strip()}
    perms: dict[str, str] = {}
    for line in text[m.end():].splitlines()[1:]:
        if not line.startswith("  ") or not line.strip():
            break
        k, _, v = line.strip().partition(":")
        perms[k.strip()] = v.strip()
    return perms


def check_workflow(text: str) -> list[str]:
    v: list[str] = []
    for no, line in enumerate(text.splitlines(), 1):
        m = USES.match(line)
        if m and not m.group(1).startswith("./") and not PINNED.match(m.group(1)):
            v.append(f"{no}: Action 을 커밋 SHA 로 고정하지 않았다 ({m.group(1)})")
    if top_permissions(text) != {"contents": "write"}:
        v.append(f"권한은 contents: write 하나여야 한다 ({top_permissions(text)})")
    if "pull_request_target" in text:
        v.append("pull_request_target 금지")
    for no, line in run_blocks(text):
        if "${{" in line:
            v.append(f"{no}: run 안에 식이 있다 — env 로 넘긴다")
        if "pip install" in line and "--require-hashes" not in line:
            v.append(f"{no}: pip 은 --require-hashes 로만 설치한다")
    checkouts = len(re.findall(r"uses:\s*actions/checkout@", text))
    if text.count("persist-credentials: false") < checkouts:
        v.append("체크아웃마다 persist-credentials: false — 토큰은 push 단계에서만 넘긴다")
    return v


GOOD = """name: t
on:
  workflow_dispatch:
permissions:
  contents: write
jobs:
  j:
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7
        with:
          persist-credentials: false
      - run: python -m pip install --require-hashes --no-deps -r requirements-lock.txt
      - env:
          T: ${{ secrets.X }}
        run: |
          echo "$T" > /dev/null
"""


def test_workflow_checker_accepts_a_clean_file():
    assert check_workflow(GOOD) == []


def test_workflow_checker_catches_unpinned_action():
    bad = GOOD.replace("@3d3c42e5aac5ba805825da76410c181273ba90b1", "@v7")
    assert any("SHA" in x for x in check_workflow(bad))


def test_workflow_checker_catches_wider_permissions():
    wider = GOOD.replace("contents: write", "contents: write\n  actions: write")
    assert any("권한" in x for x in check_workflow(wider))
    assert any("권한" in x for x in check_workflow(GOOD.replace("permissions:\n  contents: write",
                                                                "permissions: write-all")))


def test_workflow_checker_catches_expressions_inside_run():
    bad = GOOD.replace('echo "$T" > /dev/null', 'echo "${{ inputs.cap }}"')
    assert any("run 안에 식" in x for x in check_workflow(bad))
    one_line = GOOD.replace('        run: |\n          echo "$T" > /dev/null',
                            '        run: echo ${{ github.event.issue.title }}')
    assert any("run 안에 식" in x for x in check_workflow(one_line))


def test_workflow_checker_catches_persisted_credentials():
    bad = GOOD.replace("        with:\n          persist-credentials: false\n", "")
    assert any("persist-credentials" in x for x in check_workflow(bad))


def test_workflow_checker_catches_unpinned_pip_install():
    bad = GOOD.replace("--require-hashes --no-deps -r requirements-lock.txt", "-r requirements.txt")
    assert any("require-hashes" in x for x in check_workflow(bad))


def test_lock_file_pins_every_package_with_a_hash():
    lock = (PROJECT_ROOT / "requirements-lock.txt").read_text(encoding="ascii")
    pins = re.findall(r"^([a-z0-9-]+)==(\S+) \\\n    --hash=sha256:[0-9a-f]{64}$", lock, re.M)
    names = {n for n, _ in pins}
    assert "anthropic" in names and len(pins) == len(re.findall(r"^[a-z0-9-]+==", lock, re.M))
    ver = dict(pins)["anthropic"]
    major, minor = (int(x) for x in ver.split(".")[:2])
    assert major == 1 and minor >= 17       # requirements.txt 의 anthropic>=1.17,<2 안


def test_workflow_checker_catches_pull_request_target():
    assert any("pull_request_target" in x for x in check_workflow(GOOD.replace("workflow_dispatch:",
                                                                                "pull_request_target:")))


def test_workflow_files_follow_the_rules():
    files = sorted((PROJECT_ROOT / ".github" / "workflows").glob("*.yml"))
    assert files, "워크플로가 없다"
    for f in files:
        assert check_workflow(f.read_text(encoding="utf-8")) == [], f.name


def test_workflow_weekly_runs_on_monday_midnight_utc():
    # 결정 32 · P5-8 — 월 00:00 UTC(09:00 KST). 손으로 점검·실행하는 길(workflow_dispatch)도 남긴다
    text = (PROJECT_ROOT / ".github" / "workflows" / "weekly.yml").read_text(encoding="utf-8")
    on = text[text.index("\non:"):text.index("\npermissions:")]
    assert re.search(r"^  schedule:\n    - cron: \"0 0 \* \* 1\"$", on, re.M)
    assert "workflow_dispatch:" in on
