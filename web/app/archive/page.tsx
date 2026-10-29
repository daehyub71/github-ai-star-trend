import type { Metadata } from "next";
import Link from "next/link";
import type { CSSProperties } from "react";

import { ArchiveWeeks } from "@/components/ArchiveWeeks";
import { SiteFooter, SiteHeader } from "@/components/SiteHeader";
import { archiveRow, barHeights, monthLabels } from "@/lib/archive";
import { briefingWeeks, loadIndex, loadWeek } from "@/lib/data";
import { fmtInt, mmdd } from "@/lib/format";
import { hueVars } from "@/lib/palette";

export const metadata: Metadata = { title: "주간 아카이브 — GitHub AI 스타 트렌드" };

// 주간 아카이브 — 시안 v1.4: 52주 막대(높이 = AI 1위 증가, 제곱근 눈금 · 색 = 1위 카테고리) + 달별 주 카드
export default function ArchivePage() {
  const index = loadIndex();
  const names = Object.fromEntries(index.categories.map((c) => [c.id, c.name]));
  const briefs = new Set(briefingWeeks());
  const rows = index.weeks.map((w) => archiveRow(loadWeek(w), briefs.has(w)));
  const heights = barHeights(rows.map((r) => r.gain), 128);
  const big = rows.reduce((a, r) => (r.gain > a.gain ? r : a), rows[0]);
  const months = monthLabels(rows.map((r) => r.week));

  return (
    <>
      <div className="top top-archive">
        <SiteHeader current="archive" />
        <section className="hero column-hero" aria-labelledby="archive-title">
          <span className="pill sky"><span className="live" />주간 아카이브</span>
          <h1 id="archive-title">지난 <span className="grad-text">{rows.length}주</span>의 흐름</h1>
          <p className="lede">매주 월요일 09:00 KST 에 지난 주(UTC 일~토)를 정리한다. 막대 하나가 한 주 — 높이는 그 주 AI 탭 &quot;지금 뜨는&quot; 1위의 증가량, 색은 그 저장소의 카테고리.</p>
          <div className="stats narrow">
            <div className="stat"><span className="v v2">{rows.length}주</span><span className="l">{rows[0]?.week} 주부터 · 매주 월 09:00 KST</span></div>
            {big ? <div className="stat"><span className="v v0">+{fmtInt(big.gain)}</span><span className="l">가장 큰 한 주 · {big.top?.split("/")[1]} ({mmdd(big.week)} 주)</span></div> : null}
            <div className="stat"><span className="v v1">{rows.filter((r) => r.brief).length}주</span><span className="l">브리핑이 있는 주 — 나머지는 코드 요약</span></div>
          </div>
        </section>
      </div>

      <main className="page overlap">
        <section className="panel chart-panel" aria-labelledby="bars-title">
          <div className="panel-head">
            <h2 id="bars-title">주마다 AI 1위 증가량</h2>
            <span className="muted small">높이는 제곱근 눈금 — 큰 주가 작은 주를 가리지 않게 · ● 브리핑 있는 주</span>
          </div>
          <div className="bars52" role="img" aria-label={big ? `${rows.length}주 동안 주마다 AI 1위 증가량. 가장 큰 주는 ${mmdd(big.week)} 주 ${big.top} +${fmtInt(big.gain)}` : "AI 1위 증가량"}>
            {rows.map((r, i) => (
              <Link key={r.week} href={`/week/${r.week}`} className="b52" style={hueVars(r.topCat) as CSSProperties}
                title={`${mmdd(r.week)} – ${mmdd(r.end)} · ${r.top ?? "—"} +${fmtInt(r.gain)}${r.topCat ? ` · ${names[r.topCat] ?? r.topCat}` : ""}`}
                aria-label={`${r.week} 주`}>
                <span className="dot" style={{ visibility: r.brief ? "visible" : "hidden" }}>●</span>
                <span className="bar" style={{ height: `${heights[i]}px` }} />
              </Link>
            ))}
          </div>
          <div className="bars52-axis" aria-hidden="true">
            {months.map((m, i) => <span key={rows[i].week}>{m}</span>)}
          </div>
        </section>

        <ArchiveWeeks rows={rows} names={names} />
        <SiteFooter />
      </main>
    </>
  );
}
