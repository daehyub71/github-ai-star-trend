"use client";

// 4축 랭킹 카드 — AI/전체 탭(기본 AI, 결정 33), 축마다 5개 · 펼치면 15개
import Link from "next/link";
import { useState } from "react";

import type { Row, Section } from "@/lib/rankings";

import { Chip } from "./Chip";

const SHOWN = 5;

function RankRow({ row, rank, axis }: { row: Row; rank: number; axis: string }) {
  const body = (
    <>
      <span className="rank-no">{rank}</span>
      <span className="rank-main">
        <span className="rank-name"><span className="owner">{row.owner}</span>{row.repo}</span>
        <span className="rank-desc">{row.desc}</span>
        <span className="chips">{row.chips.map((c, i) => <Chip key={i} chip={c} />)}</span>
      </span>
      <span className="rank-value">
        <span className={axis === "total" ? "value" : "value up"}>{row.value}</span>
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
            <section key={s.key} className="panel rank-panel" role="region" aria-labelledby={titleId}>
              <div className="panel-head">
                <h2 id={titleId}>{s.title}</h2>
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
