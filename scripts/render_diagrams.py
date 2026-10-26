"""docs/diagrams/*.html → docs/img/*.png

헤드리스 Edge/Chrome 의 스크린샷 기능을 쓴다 — 패키지 추가 0 (SPEC NFR-13).
그림 크기는 각 HTML 의 <meta name="diagram-size" content="가로x세로"> 로 정한다.
원본 HTML 을 고치고 이 스크립트를 다시 돌리면 PNG 가 갱신된다.

    .\\.venv\\Scripts\\python.exe scripts\\render_diagrams.py            # 전부
    .\\.venv\\Scripts\\python.exe scripts\\render_diagrams.py spec-4-1    # 이름 일부로 골라서
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "diagrams"
OUT = ROOT / "docs" / "img"
SCALE = 2  # 문서에서 확대해도 글자가 깨지지 않게 2배로 찍는다

_BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]
_SIZE = re.compile(r'<meta\s+name="diagram-size"\s+content="(\d+)x(\d+)"')


def find_browser() -> str:
    for p in _BROWSERS:
        if Path(p).exists():
            return p
    for name in ("msedge", "google-chrome", "chromium", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit("Edge 또는 Chrome 을 찾지 못했다")


def diagram_size(html: Path) -> tuple[int, int]:
    m = _SIZE.search(html.read_text(encoding="utf-8"))
    if not m:
        raise SystemExit(f'{html.name}: <meta name="diagram-size" content="WxH"> 가 없다')
    return int(m.group(1)), int(m.group(2))


def render(html: Path, png: Path, browser: str) -> None:
    w, h = diagram_size(html)
    png.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as profile:
        cmd = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-first-run",
            f"--force-device-scale-factor={SCALE}",
            f"--window-size={w},{h}",
            f"--user-data-dir={profile}",
            f"--screenshot={png}",
            html.as_uri(),
        ]
        subprocess.run(cmd, check=True, timeout=120, capture_output=True)
    if not png.exists():
        raise SystemExit(f"{png.name} 가 만들어지지 않았다")


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    browser = find_browser()
    sources = sorted(SRC.glob("*.html"))
    if argv:
        sources = [s for s in sources if any(a in s.stem for a in argv)]
    for html in sources:
        png = OUT / f"{html.stem}.png"
        render(html, png, browser)
        print(f"{html.name} -> docs/img/{png.name} ({png.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
