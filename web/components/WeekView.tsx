// 이번 주 화면 — 시안 v1.1: 주 선택 · 주간 브리핑(헤드라인·세 줄·뜨는 카테고리 막대) · AI/전체 탭 4축 랭킹
// 서버 컴포넌트: 데이터는 여기서 읽고, 클라이언트(RankingSections)에는 화면에 쓰는 행만 넘긴다(NFR-6)
import Link from "next/link";

import { loadBriefing, loadCardIndex, loadIndex, loadWeek } from "@/lib/data";
import { weekRange } from "@/lib/format";
import { parseBriefing } from "@/lib/markdown";
import { buildSections, catBars, codeFacts } from "@/lib/rankings";

import { Markdown } from "./Markdown";
import { RankingSections } from "./RankingSections";
import { SiteFooter, SiteHeader } from "./SiteHeader";

export function WeekView({ week }: { week: string }) {
  const index = loadIndex();
  const data = loadWeek(week);
  const names = Object.fromEntries(index.categories.map((c) => [c.id, c.name]));
  const cards = new Set(loadCardIndex().map((c) => c.slug));
  const sections = buildSections(data, names, cards);
  const i = index.weeks.indexOf(week);
  const prev = i > 0 ? index.weeks[i - 1] : null;
  const next = i >= 0 && i < index.weeks.length - 1 ? index.weeks[i + 1] : null;
  const raw = loadBriefing(week);
  const brief = raw ? parseBriefing(raw) : null;
  const facts = brief ? null : codeFacts(data, names);
  const bars = catBars(data, names);

  return (
    <>
      <SiteHeader current="week" />
      <main className="page">
        <div className="week-head">
          <div className="when">
            <span className="muted">{i === index.weeks.length - 1 ? "지난 주" : "그 주"} · UTC 일~토</span>
            <span className="range">{weekRange(data.week, data.week_end)}</span>
          </div>
          <nav className="week-nav" aria-label="주 이동">
            {prev ? <Link className="btn" href={`/week/${prev}`}>‹ 이전 주</Link>
              : <span className="btn" aria-disabled="true">‹ 이전 주</span>}
            {next ? <Link className="btn" href={`/week/${next}`}>다음 주 ›</Link>
              : <span className="btn" aria-disabled="true">다음 주 ›</span>}
          </nav>
        </div>

        <section aria-labelledby="brief-title" className="panel brief">
          <div className="brief-main">
            <span className="brief-label">{brief ? "주간 브리핑" : "이번 주 요약 · 코드가 계산한 사실"}</span>
            <h1 id="brief-title">{brief ? brief.headline : facts?.headline}</h1>
            <ol>
              {(brief ? brief.whyNow : facts?.items ?? []).slice(0, 3).map((text, k) => (
                <li key={k}>
                  <span className="no">{String(k + 1).padStart(2, "0")}</span>
                  {brief ? <Markdown>{text}</Markdown> : <span>{text}</span>}
                </li>
              ))}
            </ol>
            <div className="brief-links">
              {brief ? <Link href={`/week/${week}/briefing`}>브리핑 전체 읽기 →</Link> : null}
              <Link href="/trends">카테고리 추이 →</Link>
            </div>
          </div>
          <div className="cat-side">
            <div>
              <strong>이번 주 뜨는 카테고리</strong>
              <div className="muted small">AI 탭 &quot;지금 뜨는&quot; 15개 중 개수</div>
            </div>
            {bars.length ? bars.map((b) => (
              <div className="bar-row" key={b.label}>
                <span>{b.label}</span>
                <span className="n">{b.count}</span>
                <div className="bar-track"><div className="bar-fill" style={{ width: b.width }} /></div>
              </div>
            )) : <span className="muted">AI 탭 판정 전</span>}
          </div>
        </section>

        <RankingSections sections={sections} />
        <SiteFooter asOf={data.week_end} />
      </main>
    </>
  );
}
