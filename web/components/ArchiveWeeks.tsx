"use client";

// 주간 아카이브의 주 카드 목록 — 최근 12주 / 52주 전체, 달로 묶어 최신 주부터 (시안 v1.4)
import Link from "next/link";
import { useState, type CSSProperties } from "react";

import { monthGroups, type ArchiveRow } from "@/lib/archive";
import { fmtInt, mmdd, splitName } from "@/lib/format";
import { hueVars } from "@/lib/palette";

const RECENT = 12;

export function ArchiveWeeks({ rows, names }: { rows: ArchiveRow[]; names: Record<string, string> }) {
  const [all, setAll] = useState(false);
  const newest = [...rows].sort((a, b) => b.week.localeCompare(a.week));
  const groups = monthGroups(all ? newest : newest.slice(0, RECENT));
  return (
    <>
      <div className="tabs-bar">
        <div role="group" aria-label="기간" className="seg">
          <button type="button" aria-pressed={!all} onClick={() => setAll(false)}>최근 {RECENT}주</button>
          <button type="button" aria-pressed={all} onClick={() => setAll(true)}>{rows.length}주 전체</button>
        </div>
        <span className="muted">최신 주가 먼저 · 브리핑이 없는 주는 코드가 계산한 사실 요약으로 열린다</span>
      </div>
      {groups.map((g) => (
        <section key={g.key} className="month" aria-label={g.label}>
          <h2>{g.label}<span className="muted small">{g.rows.length}주</span></h2>
          <div className="week-grid">
            {g.rows.map((r) => {
              const { owner, repo } = splitName(r.top ?? "");
              return (
                <Link key={r.week} href={`/week/${r.week}`} className="week-card" style={hueVars(r.lead) as CSSProperties}>
                  <span className="wc-head">
                    <span className="mono range">{mmdd(r.week)} – {mmdd(r.end)}</span>
                    <span className={r.brief ? "wc-badge brief" : "wc-badge"}>{r.brief ? "브리핑" : "코드 요약"}</span>
                  </span>
                  <span className="wc-top">
                    <span className="small muted">AI 1위 · 지금 뜨는</span>
                    {r.top ? (
                      <>
                        <span className="rank-name"><span className="owner">{owner}</span>{repo}</span>
                        <span className="wc-gain mono">+{fmtInt(r.gain)}</span>
                      </>
                    ) : <span className="muted">AI 탭 판정 전</span>}
                  </span>
                  <span className="chips">
                    {r.lead ? <span className="chip chip-cat">{names[r.lead] ?? r.lead}</span> : null}
                    <span className="small muted">AI 저장소 {r.n}개</span>
                  </span>
                  {r.fresh ? <span className="wc-fresh">새로 뜬 1위 · {r.fresh}</span> : null}
                </Link>
              );
            })}
          </div>
        </section>
      ))}
      {!all && rows.length > RECENT ? (
        <button type="button" className="toggle wide" onClick={() => setAll(true)}>{rows.length}주 모두 보기</button>
      ) : null}
    </>
  );
}
