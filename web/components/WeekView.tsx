// 이번 주 화면 — 시안 v1.3: 어두운 히어로(헤드라인·숫자 3개·이미지) · 핵심 3가지 + 뜨는 카테고리 · 이번 주 카드 · 4축 랭킹
// 서버 컴포넌트: 데이터는 여기서 읽고, 클라이언트(RankingSections·WeekCards)에는 화면에 쓰는 것만 넘긴다(NFR-6)
import Link from "next/link";
import type { CSSProperties } from "react";

import { artUrl } from "@/lib/art";
import { cardSlugsForWeek, weekCardList } from "@/lib/cards";
import { loadBriefing, loadCard, loadCardIndex, loadIndex, loadWeek } from "@/lib/data";
import { weekRange } from "@/lib/format";
import { cardSummary, parseBriefing, type CardBrief } from "@/lib/markdown";
import { hueVars, paletteOf } from "@/lib/palette";
import { buildSections, catBars, codeFacts, heroStats } from "@/lib/rankings";

import { HeroArt } from "./HeroArt";
import { Markdown } from "./Markdown";
import { RankingSections } from "./RankingSections";
import { SiteFooter, SiteHeader } from "./SiteHeader";
import { WeekCards } from "./WeekCards";

export function WeekView({ week }: { week: string }) {
  const index = loadIndex();
  const data = loadWeek(week);
  const names = Object.fromEntries(index.categories.map((c) => [c.id, c.name]));
  const shown = cardSlugsForWeek(data);
  const briefs = new Map<string, CardBrief>();
  for (const ref of loadCardIndex()) {
    if (!shown.has(ref.slug)) continue;
    const md = loadCard(ref.slug);
    if (md) briefs.set(ref.slug, cardSummary(md));
  }
  const whyBySlug = new Map([...briefs].map(([slug, b]) => [slug, b.why]));
  const sections = buildSections(data, names, whyBySlug);
  const cards = weekCardList(data, briefs, names).map((c) => ({ ...c, cover: artUrl(paletteOf(c.catId).slot) }));
  const i = index.weeks.indexOf(week);
  const prev = i > 0 ? index.weeks[i - 1] : null;
  const next = i >= 0 && i < index.weeks.length - 1 ? index.weeks[i + 1] : null;
  const raw = loadBriefing(week);
  const brief = raw ? parseBriefing(raw) : null;
  const facts = brief ? null : codeFacts(data, names);
  const bars = catBars(data, names);
  const max = bars[0]?.count ?? 1;
  const stats = heroStats(data, cards.length);
  const accents = ["linear-gradient(135deg,#8B5CF6,#EC4899)", "linear-gradient(135deg,#3B82F6,#6366F1)",
    "linear-gradient(135deg,#F97316,#EAB308)"];

  return (
    <>
      <div className="top top-week">
        <SiteHeader current="week" />
        <section aria-labelledby="brief-title" className="hero">
          <div className="hero-text">
            <div className="hero-meta">
              <span className="pill"><span className="live" />{brief ? "주간 브리핑" : "이번 주 요약 · 코드가 계산한 사실"}</span>
              <span>{weekRange(data.week, data.week_end)} · UTC 일~토</span>
            </div>
            <h1 id="brief-title">{brief ? brief.headline : facts?.headline}</h1>
            <div className="stats">
              {stats.map((s, k) => (
                <div className="stat" key={s.label}>
                  <span className={`v v${k}`}>{s.value}</span>
                  <span className="l">{s.label}</span>
                </div>
              ))}
            </div>
            <div className="hero-actions">
              {brief ? <Link className="btn-primary" href={`/week/${week}/briefing`}>브리핑 전체 읽기 →</Link> : null}
              <Link className="btn-ghost" href="/trends">저장소 추이 →</Link>
              <nav className="week-nav" aria-label="주 이동">
                {prev ? <Link className="btn-ghost sm" href={`/week/${prev}`}>‹ 이전 주</Link>
                  : <span className="btn-ghost sm" aria-disabled="true">‹ 이전 주</span>}
                {next ? <Link className="btn-ghost sm" href={`/week/${next}`}>다음 주 ›</Link>
                  : <span className="btn-ghost sm" aria-disabled="true">다음 주 ›</span>}
              </nav>
            </div>
          </div>
          <div className="hero-art">
            <HeroArt src={artUrl("hero-home")} />
          </div>
        </section>
      </div>

      <main className="page overlap">
        <section className="panel brief-panel" aria-label="이번 주 핵심">
          <div className="brief-main">
            <h2>이번 주 핵심 3가지 {brief ? <span className="ai-badge">AI 작성</span> : null}</h2>
            <ol>
              {(brief ? brief.whyNow : facts?.items ?? []).slice(0, 3).map((text, k) => (
                <li key={k}>
                  <span className="no" style={{ background: accents[k] }}>{String(k + 1).padStart(2, "0")}</span>
                  {brief ? <Markdown>{text}</Markdown> : <span>{text}</span>}
                </li>
              ))}
            </ol>
          </div>
          <div className="cat-side">
            <div>
              <strong>이번 주 뜨는 카테고리</strong>
              <div className="muted small">AI 탭 &quot;지금 뜨는&quot; 15개 중 개수</div>
            </div>
            {bars.length ? bars.map((b) => (
              <div className="bar-row" key={b.id} style={hueVars(b.id) as CSSProperties}>
                <span className="lab"><span className="sw" />{b.label}</span>
                <span className="n">{b.count}</span>
                <div className="bar-track"><div className="bar-fill" style={{ width: `${(b.count / max) * 100}%` }} /></div>
              </div>
            )) : <span className="muted">AI 탭 판정 전</span>}
          </div>
        </section>

        <WeekCards cards={cards} />
        <RankingSections sections={sections} />
        <SiteFooter asOf={data.week_end} />
      </main>
    </>
  );
}
