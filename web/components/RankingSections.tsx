"use client";

// 4축 랭킹 카드 — AI/전체 탭(기본 AI, 결정 33), 축마다 5개 · 펼치면 15개
// 시안 v1.3: 1~3위 메달, 축마다 색·아이콘, 카드가 있는 행에 '왜 지금' 한 줄
import Link from "next/link";
import { useState } from "react";

import type { Row, Section } from "@/lib/rankings";

import { Chip } from "./Chip";

const SHOWN = 5;

// 불꽃(증가) · 새싹(신규) · 오르는 화살표(성장률) · 별(누적)
const ICON: Record<string, string> = {
  gain: "M12 3c1 3.5 4.5 5 4.5 9.5A4.5 4.5 0 0 1 12 17a4.5 4.5 0 0 1-4.5-4.5c0-2 1-3.2 2-4 0 1.5.8 2.5 2 2.5 0-3 .5-5.5.5-8z M6 20h12",
  fresh: "M12 21v-9 M12 12c0-4 3-7 7-7 0 4-3 7-7 7z M12 14c0-3-2.5-5.5-6-5.5 0 3 2.5 5.5 6 5.5z",
  growth: "M4 18l6-6 4 4 6-8 M14 8h6v6",
  total: "M12 3l2.6 5.6 6.1.7-4.5 4.2 1.2 6L12 16.6 6.6 19.5l1.2-6L3.3 9.3l6.1-.7z",
};

function RankRow({ row, rank, axis }: { row: Row; rank: number; axis: string }) {
  const body = (
    <>
      <span className={rank <= 3 ? `rank-no medal-${rank}` : "rank-no"}>{rank}</span>
      <span className="rank-main">
        <span className="rank-name"><span className="owner">{row.owner}</span>{row.repo}</span>
        <span className="rank-desc">{row.desc}</span>
        <span className="chips">{row.chips.map((c, i) => <Chip key={i} chip={c} />)}</span>
        {row.hasCard && row.why ? <span className="why"><b>왜 지금 · </b>{row.why}</span> : null}
      </span>
      <span className="rank-value">
        <span className={`value v-${axis}`}>{row.value}</span>
        <span className="sub">{row.sub}</span>
      </span>
    </>
  );
  // 카드가 있으면 사이트 안 카드로, 없으면 GitHub 으로
  return row.href.startsWith("http")
    ? <a className="rank-row" href={row.href} target="_blank" rel="noopener noreferrer">{body}</a>
    : <Link className="rank-row" href={row.href}>{body}</Link>;
}

export function RankingSections({ sections }: { sections: Section[] }) {
  const [tab, setTab] = useState<"ai" | "all">("ai");
  const [open, setOpen] = useState<Record<string, boolean>>({});
  return (
    <>
      <div className="tabs-bar">
        <div role="group" aria-label="저장소 범위" className="seg">
          {(["ai", "all"] as const).map((t) => (
            <button key={t} type="button" aria-pressed={tab === t} onClick={() => setTab(t)}>
              {t === "ai" ? "AI" : "전체"}
            </button>
          ))}
        </div>
        <span className="muted">
          {tab === "ai" ? "AI 탭 — LLM 판정 기준 · 축마다 AI 저장소 15개" : "전체 탭 — 스타 1,000 이상 후보와 30일 이내 새 저장소"}
        </span>
      </div>
      <div className="rank-grid">
        {sections.map((s) => {
          const list = tab === "ai" ? s.ai : s.all;
          const expanded = !!open[s.key];
          const rows = list ? (expanded ? list : list.slice(0, SHOWN)) : [];
          const titleId = `rank-${s.key}`;
          return (
            <section key={s.key} className={`panel rank-panel axis-${s.key}`} role="region" aria-labelledby={titleId}>
              <div className="panel-head">
                <h2>
                  <span className="axis-icon" aria-hidden="true">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2"
                      strokeLinecap="round" strokeLinejoin="round"><path d={ICON[s.key]} /></svg>
                  </span>
                  <span id={titleId}>{s.title}</span>
                </h2>
                <span className="muted small">{s.def}</span>
              </div>
              {list === null ? (
                <p className="note">AI 탭은 아직 판정 전이다 — 분류(classify)가 끝나면 채워진다.</p>
              ) : (
                rows.map((r, i) => <RankRow key={r.key} row={r} rank={i + 1} axis={s.key} />)
              )}
              {s.note && list !== null ? <p className="note">{s.note}</p> : null}
              {list !== null && list.length > SHOWN ? (
                <button type="button" className="toggle" aria-expanded={expanded}
                  onClick={() => setOpen({ ...open, [s.key]: !expanded })}>
                  {expanded ? "접기" : "펼치기 · 15위까지"}
                </button>
              ) : null}
            </section>
          );
        })}
      </div>
    </>
  );
}
