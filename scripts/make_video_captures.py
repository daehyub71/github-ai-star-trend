"""영상(실전편 T1)용 화면 캡처 7장 — docs/video/captures/src/*.html 을 만들고 PNG 로 찍는다.

숫자는 저장소의 파일에서 읽거나(TASK 대시보드 · 시험 랭킹 · 소급 로그), MEASURE 의 해당 절을 주석으로 단다.
개인 경로·계정·토큰은 넣지 않는다. 다시 만들려면:

    .\\.venv\\Scripts\\python.exe scripts\\make_video_captures.py
"""

# 이 파일은 화면용 HTML 템플릿이라 긴 줄을 그대로 둔다 (줄 길이 규칙만 이 파일에서 끈다)
# ruff: noqa: E501

import html
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "video" / "captures" / "src"
W, H = 1600, 900

CSS = """
html, body { margin: 0; background: #ffffff; }
body { width: @Wpx; height: @Hpx; box-sizing: border-box; padding: 56px 72px;
       font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', 'Segoe UI', sans-serif; color: #1b1a17; position: relative; }
h1 { font-size: 44px; margin: 0 0 6px; letter-spacing: -0.5px; }
.sub { font-size: 21px; color: #5f5b53; margin: 0 0 30px; }
.src { position: absolute; right: 72px; bottom: 30px; font-size: 16px; color: #8a8f98; }
.mono { font-family: Consolas, 'SF Mono', Menlo, monospace; }
.coral { color: #c4532f; } .teal { color: #0e7c78; } .blue { color: #2f5d9e; } .muted { color: #5f5b53; }
.card { background: #f4f5f7; border: 1px solid #e3e6eb; border-radius: 18px; padding: 26px 30px; }
.chip { display: inline-block; font-size: 16px; padding: 3px 10px; border-radius: 8px; margin: 2px 4px 2px 0;
        background: #fff4d6; color: #7a5200; border: 1px solid #f0d58c; }
table { border-collapse: collapse; width: 100%; }
td, th { padding: 9px 10px; border-bottom: 1px solid #e3e6eb; font-size: 21px; text-align: left; }
th { font-size: 17px; color: #5f5b53; font-weight: 600; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
""".replace("@W", str(W)).replace("@H", str(H))


def page(name: str, title: str, sub: str, body: str, source: str) -> None:
    doc = (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
           f'<meta name="diagram-size" content="{W}x{H}"><title>{html.escape(title)}</title>'
           f"<style>{CSS}</style></head><body><h1>{title}</h1><p class=\"sub\">{sub}</p>{body}"
           f'<div class="src">출처: {html.escape(source)}</div></body></html>')
    SRC.mkdir(parents=True, exist_ok=True)
    (SRC / f"{name}.html").write_text(doc, encoding="utf-8", newline="\n")


def task_dashboard() -> None:
    rows = []
    for line in (ROOT / "docs" / "TASK.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(\**)([^|]+?)\**\s*\|\s*`[█░]+`\s*\|\s*\**(\d+)/(\d+) \((\d+)%\)\**", line)
        if m:
            rows.append((m.group(2).strip(), int(m.group(3)), int(m.group(4)), int(m.group(5)), bool(m.group(1))))
    trs = "".join(
        f"<tr><td style='width:420px;{'font-weight:700' if bold else ''}'>{html.escape(name)}</td>"
        f"<td><div style='background:#e3e6eb;border-radius:8px;height:22px;width:640px'>"
        f"<div style='background:{'#0e7c78' if pct == 100 else '#2f5d9e'};height:22px;border-radius:8px;"
        f"width:{max(pct, 1) * 6.4:.0f}px'></div></div></td>"
        f"<td class='num' style='width:200px'>{d}/{t} ({pct}%)</td></tr>"
        for name, d, t, pct, bold in rows)
    page("sT1_task", "진도율 대시보드", "완료(<b>[x]</b>)만 센다 · 2026-10-27 기준",
         f"<table>{trs}</table>", "docs/TASK.md 진도율 대시보드")


def measure() -> None:
    # MEASURE §0·§1 (후보 규모) · §2 (수집 방식별 주간 비용)
    body = """
<div style="display:grid;grid-template-columns:1fr 1fr;gap:34px">
 <div class="card"><div class="muted" style="font-size:22px">후보 저장소 (스타 1,000 이상)</div>
  <div style="font-size:30px;margin-top:22px">짐작 <span class="muted">약 2만 개</span></div>
  <div style="font-size:24px;margin:10px 0" class="muted">↓ 비용 0 실측</div>
  <div style="font-size:64px;font-weight:700" class="coral">65,922개</div>
  <div class="muted" style="font-size:19px;margin-top:14px">500 이상 125,024 · 100 이상 486,361</div></div>
 <div class="card"><div class="muted" style="font-size:22px">매주 스타 변화를 모으는 방법</div>
  <table style="margin-top:18px">
   <tr><th>방법</th><th class="num">요청</th><th class="num">시간</th></tr>
   <tr><td>저장소마다 히스토리</td><td class="num">65,922회</td><td class="num coral" style="font-weight:700">13.2시간</td></tr>
   <tr><td>Search 스냅샷</td><td class="num">660쪽</td><td class="num teal" style="font-weight:700">22분</td></tr>
  </table>
  <div style="font-size:24px;margin-top:22px">→ 스냅샷 차이 + <b>상위만</b> 히스토리</div></div>
</div>
<div style="font-size:26px;margin-top:36px">원칙 — <b>측정 전에 설계를 확정하지 않는다.</b> 비용 0 으로 잴 수 있는 단계를 먼저 만든다.</div>"""
    page("sT1_measure", "짐작 대신 줄자", "probe 실측 · 2026-10-26", body, "docs/MEASURE.md §0 · §1 · §2")


def discover() -> None:
    # MEASURE §12 (첫 discover 실행) — 641 은 첫 실행의 누락 수
    body = """
<div style="display:grid;grid-template-columns:1.05fr 1fr;gap:34px;align-items:start">
 <div class="card"><div class="muted" style="font-size:22px">첫 실행 — 에러 메시지 없이</div>
  <div style="font-size:150px;font-weight:800;line-height:1.05" class="coral">641</div>
  <div style="font-size:26px">개가 비어 있었다</div>
  <table style="margin-top:22px"><tr><td>Search 요청</td><td class="num">1,167회 · 57분</td></tr>
   <tr><td>기대 (스타 ≥1,000)</td><td class="num">65,924개</td></tr>
   <tr><td>고친 뒤</td><td class="num teal" style="font-weight:700">65,921개 · 누락 3 (0.005%)</td></tr>
   <tr><td>전체 스냅샷</td><td class="num">82,590개</td></tr></table></div>
 <div><div style="font-size:24px;font-weight:700;margin-bottom:14px">세 가지 원인 → 고친 것</div>
  <div class="card" style="margin-bottom:14px;font-size:21px">① 99개만 온 쪽에서 멈췄다<br><span class="teal">→ 빈 쪽에서만 멈춘다</span></div>
  <div class="card" style="margin-bottom:14px;font-size:21px">② 시간 초과로 일부만 온 응답이 캐시에 남았다<br><span class="teal">→ 저장하지 않고 한 번 더 받는다</span></div>
  <div class="card" style="font-size:21px">③ 스타 수가 같으면 쪽 경계가 흔들렸다<br><span class="teal">→ 100개 이하로 쪼개 한 쪽에 받는다</span></div>
  <div style="font-size:20px;margin-top:16px" class="muted">고치기 전에 재현 테스트부터(RED → GREEN)</div></div>
</div>"""
    page("sT1_discover", "첫 실제 실행 — 641개가 사라졌다", "discover · 2026-10-26 · 2026-10-18 주 스냅샷",
         body, "docs/MEASURE.md §12")


def tests() -> None:
    # 2026-10-27 커밋 0218cc3 의 커밋 전 검사 출력 (경로는 프로젝트 이름만)
    dots = "." * 72
    lines = [("cmd", "PS github-ai-star-trend> ruff check ."), ("ok", "All checks passed!"),
             ("cmd", "PS github-ai-star-trend> mypy startrend tests scripts"),
             ("ok", "Success: no issues found in 69 source files"),
             ("cmd", "PS github-ai-star-trend> pytest -q"),
             ("", f"{dots} [ 24%]"), ("", f"{dots} [ 49%]"), ("", f"{dots} [ 73%]"), ("", f"{dots} [ 98%]"),
             ("", f"{'.' * 5:<72} [100%]"), ("ok", "293 passed, 4 deselected in 5.73s")]
    color = {"cmd": "#9cdcfe", "ok": "#6ad38e", "": "#d4d4d4"}
    pre = "\n".join(f"<span style='color:{color[k]}'>{html.escape(t)}</span>" for k, t in lines)
    body = (f"<pre class='mono' style='background:#1e1f22;border-radius:16px;padding:30px 34px;font-size:22px;"
            f"line-height:1.5;margin:0'>{pre}</pre>"
            "<div style='font-size:22px;margin-top:22px'>기본 테스트는 <b>인터넷 · 키 · 돈 없이</b> 통과한다 · "
            "실제 호출 4개는 <span class='mono'>-m live</span> 로만</div>")
    page("sT1_tests", "테스트가 지키는 규칙", "커밋 전 검사: ruff → mypy → pytest → 크기 가드", body,
         "커밋 전 훅 출력 (2026-10-27)")


def ranking() -> None:
    p = ROOT / ".work" / "trial-data2" / "weekly" / "2026-10-18" / "rankings.json"
    d = json.loads(p.read_text(encoding="utf-8"))

    def table(axis: str, metric: str) -> str:
        trs = []
        for e in d["axes"][axis]["all"][:5]:
            chips = "".join(f"<span class='chip'>{html.escape(f['label'])}</span>" for f in e["flags"])
            val = f"+{e['gain']:,}" if metric == "gain" else f"{e['stars_end']:,}"
            trs.append(f"<tr><td class='num' style='width:30px'>{e['rank']}</td>"
                       f"<td class='mono' style='font-size:19px'>{html.escape(e['full_name'])}<br>{chips}</td>"
                       f"<td class='num coral' style='font-weight:700'>{val}</td></tr>")
        return f"<table>{''.join(trs)}</table>"

    body = f"""
<div style="display:grid;grid-template-columns:1fr 1fr;gap:34px">
 <div><div style="font-size:24px;font-weight:700;margin-bottom:6px">이번 주 증가 TOP 5</div>{table("gain", "gain")}</div>
 <div><div style="font-size:24px;font-weight:700;margin-bottom:6px">새로 뜨는 (30일 이내) TOP 5 · 누적 스타</div>{table("fresh", "stars")}</div>
</div>
<div style="font-size:21px;margin-top:20px">노란 표시는 <b>순위에서 빼지 않고</b> 근거 숫자만 붙인다 (결정 28 · 40)</div>"""
    page("sT1_rank", "첫 랭킹 — 2026-10-18 주", "시험 소급 4주 · 저장소 3,495개 · 21분 · 비용 0 (전체 탭)",
         body, "시험 소급 랭킹 rankings.json · docs/MEASURE.md §13")


def backfill_log() -> None:
    log = (ROOT / ".work" / "backfill-full2.log").read_text(encoding="utf-8-sig")
    progress = [ln.strip() for ln in log.splitlines() if "/82590" in ln][-4:]
    pre = "\n".join(html.escape(x) for x in progress)
    # 타임라인 — MEASURE §14 · 캐시된 응답 헤더(레이트 리밋 창)
    body = f"""
<div style="display:grid;grid-template-columns:1.1fr 1fr;gap:34px;align-items:start">
 <div class="card" style="font-size:21px;line-height:1.75">
  <b>10-26 16:21</b> 52주 소급 시작 — 저장소 82,590개 · 약 15만 번<br>
  <b>10-27 06:40</b> <span class="coral">14시간째 · 36,000개에서 종료</span><br>
  &nbsp;&nbsp;&nbsp;상대 서버가 응답 없이 연결을 끊음 (RemoteDisconnected)<br>
  &nbsp;&nbsp;&nbsp;주간 파일은 0개 — 반쯤 쓴 파일 없음<br>
  <b>06:45</b> <span class="teal">고친 코드로 이어 돌리기</span> — 받은 응답은 캐시에서<br>
  <b>14:05 → 14:36</b> 시간당 한도(5,000회) 대기 31분 — 정상<br></div>
 <div><div style="font-size:22px;font-weight:700;margin-bottom:10px">고친 것</div>
  <div class="card" style="font-size:20px;margin-bottom:14px">연결이 끊기면 2·4·8 … 64초 간격으로 6번 다시</div>
  <div class="card" style="font-size:20px;margin-bottom:14px">그래도 안 되면 <b>건너뛰지 않고 멈춘다</b><br><span class="muted">건너뛰면 한 번 쓰면 못 고치는 주간 파일에 구멍</span></div>
  <div class="card" style="font-size:20px">대기마다 이유를 로그에 남긴다</div></div>
</div>
<pre class="mono" style="background:#1e1f22;color:#d4d4d4;border-radius:14px;padding:18px 24px;font-size:20px;margin-top:24px">{pre}</pre>"""
    page("sT1_log", "52주 소급 — 끊기면 멈추고, 이어 돌린다", "1회성 · 비용 0 · GitHub 시간당 5,000회 한도",
         body, "docs/MEASURE.md §14 · 소급 로그")


def search() -> None:
    # MEASURE §15 — Claude 서버 검색 실측과 Tavily 비교 (graphify)
    claude_rows = [("cloudflare/security-audit-skill", 29055, 485, 0.156), ("Graphify-Labs/graphify", 29290, 499, 0.157),
                   ("debpalash/VoiceStudio", 29251, 605, 0.159), ("stablyai/orca", 29110, 499, 0.156),
                   ("google-research/harness2", 21213, 347, 0.122)]
    trs = "".join(f"<tr><td class='mono' style='font-size:17px'>{n}</td><td class='num'>{i:,}</td>"
                  f"<td class='num coral' style='font-weight:700'>0</td><td class='num'>${c:.3f}</td></tr>"
                  for n, i, _o, c in claude_rows)
    found = ["wavect.io — 리뷰", "kevinkinnett.com — 사용기", "augmentcode.com — 기사",
             "youtube.com — 영상", "dev.to — 튜토리얼", "pub.towardsai.net — 비교"]
    lis = "".join(f"<div style='font-size:20px;margin:6px 0'>✓ {html.escape(x)}</div>" for x in found)
    body = f"""
<div style="display:grid;grid-template-columns:1.25fr 1fr;gap:30px;align-items:start">
 <div class="card"><div style="font-size:22px;font-weight:700">① Claude 에게 검색까지 (서버 쪽 웹 검색)</div>
  <table style="margin-top:10px"><tr><th>저장소</th><th class="num">입력 토큰</th><th class="num">출처</th><th class="num">비용</th></tr>{trs}</table>
  <div style="font-size:19px;margin-top:12px" class="muted">검색 3번씩 · 합계 $0.75 · 원인: 검색 코드 오류 + 같은 검색어 반복 → 횟수 제한</div></div>
 <div class="card"><div style="font-size:22px;font-weight:700">② 우리 코드가 검색 (Tavily)</div>
  <div class="mono" style="font-size:18px;margin:8px 0 6px">Graphify-Labs/graphify</div>
  <div style="font-size:34px;font-weight:700" class="teal">1크레딧 · 1.7초 · 6건</div>{lis}
  <div style="font-size:18px;margin-top:8px" class="muted">+ 저장소 자체 1건 · 무관 1건 (Claude 판정이 거름)</div></div>
</div>
<div style="font-size:23px;margin-top:22px">결정 46 — <b>검색은 우리 코드가, 판정·요약은 Claude 가</b> (근거 목록 파일 → 인용 게이트)</div>"""
    page("sT1_search", "누가 검색하나", "D-7 실측 · 2026-10-27 · 승인 상한 $3 중 $0.91 사용", body,
         "docs/MEASURE.md §15")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    for make in (task_dashboard, measure, discover, tests, ranking, backfill_log, search):
        make()
    return subprocess.call([sys.executable, str(ROOT / "scripts" / "render_diagrams.py"),
                            "--src", "docs/video/captures/src", "--out", "docs/video/captures"])


if __name__ == "__main__":
    raise SystemExit(main())
