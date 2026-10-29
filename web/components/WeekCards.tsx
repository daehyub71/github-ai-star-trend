"use client";

// '이번 주 카드' — 시안 v1.3. 카테고리 커버(이미지가 없으면 카테고리 색 그라데이션) + 카드 ① 3줄 요약
import Link from "next/link";
import { useState, type CSSProperties } from "react";

import type { WeekCard } from "@/lib/cards";
import { hueVars } from "@/lib/palette";

const SHOWN = 6;

export type CoveredCard = WeekCard & { cover: string | null };

export function WeekCards({ cards }: { cards: CoveredCard[] }) {
  const [all, setAll] = useState(false);
  if (!cards.length) return null;
  const shown = all ? cards : cards.slice(0, SHOWN);
  return (
    <section aria-labelledby="cards-title" className="week-cards">
      <div className="section-head">
        <h2 id="cards-title">
          <span className="axis-icon grad" aria-hidden="true">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinejoin="round">
              <rect x="4" y="4" width="16" height="16" rx="3" /><path d="M8 9h8M8 13h8M8 17h5" />
            </svg>
          </span>
          이번 주 카드
        </h2>
        <span className="muted"><span className="ai-badge">AI 작성</span> AI 탭 저장소마다 심층 카드 · 사람 검토 없음, 출처는 카드 안 · 누르면 카드 전체</span>
      </div>
      <div className="card-grid">
        {shown.map((c) => (
          <Link key={c.slug} href={c.href} className="wcard" style={hueVars(c.catId) as CSSProperties}>
            <span className="cover" style={c.cover ? { backgroundImage: `url(${c.cover})` } : undefined}>
              <span className="cover-chip">{c.catName}</span>
            </span>
            <span className="wcard-body">
              <span className="rank-name"><span className="owner">{c.owner}</span>{c.repo}</span>
              <span className="tri">
                <span className="k">무엇인지</span><span className="t">{c.what}</span>
                <span className="k why-k">왜 지금</span><span className="t strong">{c.why}</span>
                <span className="k">의미</span><span className="t">{c.meaning}</span>
              </span>
              <span className="more">카드 전체 보기 →</span>
            </span>
          </Link>
        ))}
      </div>
      {cards.length > SHOWN ? (
        <button type="button" className="toggle wide" aria-expanded={all} onClick={() => setAll(!all)}>
          {all ? "접기" : `모두 보기 · ${cards.length}개`}
        </button>
      ) : null}
    </section>
  );
}
