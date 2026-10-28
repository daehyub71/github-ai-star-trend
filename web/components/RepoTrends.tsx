"use client";

// 저장소 추이 — 시안 v1.3 "꾸준히 뜨는 저장소": 기간(12·52주) · 정렬(진입한 주·최근 4주 증가·연속) · 상위 3개 타일 + 표
// 서버가 기간×정렬 6가지 목록을 미리 만들어 넘긴다(NFR-6) — 여기서는 고르기만 한다
import Link from "next/link";
import { useState, type CSSProperties, type ReactNode } from "react";

import { fmtInt, fmtSigned } from "@/lib/format";
import { hueVars } from "@/lib/palette";
import type { Period, SortKey, TrendRow } from "@/lib/repotrends";

const SHOWN = 15;
const SORTS: [SortKey, string][] = [["weeks", "진입한 주"], ["gain", "최근 4주 증가"], ["streak", "연속 진입"]];

function points(spark: number[]): { line: string; area: string } {
  const max = Math.max(1, ...spark);
  const line = spark.map((v, k) => `${k * 12},${(30 - (v / max) * 26).toFixed(1)}`).join(" ");
  return { line, area: `0,32 ${line} 132,32` };
}

function Spark({ spark, label }: { spark: number[]; label: string }) {
  const p = points(spark);
  return (
    <svg className="spark" viewBox="0 0 132 32" preserveAspectRatio="none" role="img" aria-label={label}>
      <polygon points={p.area} className="area" />
      <polyline points={p.line} className="line" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function RepoLink({ row, className, children }: { row: TrendRow; className?: string; children: ReactNode }) {
  return row.href.startsWith("http")
    ? <a className={className} href={row.href} target="_blank" rel="noopener noreferrer">{children}</a>
    : <Link className={className} href={row.href}>{children}</Link>;
}

export function RepoTrends({ views, names, header, until, footer }: {
  views: Record<string, TrendRow[]>; names: Record<string, string>; header: ReactNode; until: string; footer: ReactNode;
}) {
  const [period, setPeriod] = useState<Period>(12);
  const [sort, setSort] = useState<SortKey>("weeks");
  const [more, setMore] = useState(false);
  const rows = views[`${period}-${sort}`] ?? [];
  const shown = more ? rows : rows.slice(0, SHOWN);
  const sparkLabel = (r: TrendRow) => `최근 12주 주간 스타 ${r.spark.map(fmtInt).join(", ")}`;

  return (
    <>
      <div className="top top-trends">
        {header}
        <section className="hero trends-hero" aria-labelledby="trends-title">
          <div className="trends-head">
            <div className="trends-title">
              <span className="pill teal"><span className="live" />저장소 추이</span>
              <h1 id="trends-title">꾸준히 <span className="grad-text">뜨는</span> 저장소</h1>
              <span className="lede">AI 탭의 뜨는 축(지금 뜨는 · 새로 뜨는 · 규모 대비 급성장)에 든 주를 센다 · 누적 TOP 축은 빼고</span>
            </div>
            <div role="group" aria-label="기간" className="seg glass">
              {([12, 52] as const).map((p) => (
                <button key={p} type="button" aria-pressed={period === p} onClick={() => setPeriod(p)}>{p}주</button>
              ))}
            </div>
          </div>
          <div className="podium">
            {rows.slice(0, 3).map((r) => (
              <RepoLink key={r.fullName} row={r} className="podium-tile">
                <span className="podium-name" style={hueVars(r.catId) as CSSProperties}>
                  <span className={`rank-no medal-${r.rank}`}>{r.rank}</span>
                  <span className="rank-name"><span className="owner">{r.owner}</span>{r.repo}</span>
                </span>
                <span style={hueVars(r.catId) as CSSProperties}><Spark spark={r.spark} label={sparkLabel(r)} /></span>
                <span className="podium-foot">
                  <span><b>{r.weeks} / {period}주</b> 진입</span>
                  <span>4주 <b className="hot">{fmtSigned(r.gain4)}</b></span>
                </span>
              </RepoLink>
            ))}
          </div>
        </section>
      </div>

      <main className="page overlap">
        <section className="panel trends-panel">
          <div className="tabs-bar">
            <div role="group" aria-label="정렬" className="seg">
              {SORTS.map(([k, label]) => (
                <button key={k} type="button" aria-pressed={sort === k} onClick={() => setSort(k)}>{label}</button>
              ))}
            </div>
            <span className="muted small">{until} 주까지 {period}주 · 상위 {shown.length}개</span>
          </div>
          <div className="table-wrap">
            <table className="trends-table">
              <thead>
                <tr>
                  <th scope="col">#</th>
                  <th scope="col">저장소</th>
                  <th scope="col">진입한 주</th>
                  <th scope="col" className="num">연속</th>
                  <th scope="col" className="num">최근 4주 증가</th>
                  <th scope="col">주간 스타 · 최근 12주</th>
                  <th scope="col">카드</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.fullName} style={hueVars(r.catId) as CSSProperties}>
                    <td><span className={r.rank <= 3 ? `rank-no medal-${r.rank}` : "rank-no"}>{r.rank}</span></td>
                    <td className="repo-cell">
                      <span className="rank-name"><span className="owner">{r.owner}</span>{r.repo}</span>
                      {r.catId ? <span className="chip chip-cat">{names[r.catId] ?? r.catId}</span> : null}
                    </td>
                    <td>
                      <span className="weeks-n">{r.weeks} / {period}주</span>
                      <span className={`cells p${period}`} role="img" aria-label={`${period}주 중 ${r.weeks}주 진입`}>
                        {r.bits.split("").map((b, k) => <span key={k} className={b === "1" ? "on" : undefined} />)}
                      </span>
                    </td>
                    <td className="num">{r.streak ? `${r.streak}주` : "—"}</td>
                    <td className="num hot">{fmtSigned(r.gain4)}</td>
                    <td><Spark spark={r.spark} label={sparkLabel(r)} /></td>
                    <td>
                      {r.hasCard ? <Link className="card-pill" href={r.href}>카드 보기 →</Link>
                        : <a className="gh-link" href={r.href} target="_blank" rel="noopener noreferrer">GitHub ↗</a>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {rows.length > SHOWN ? (
            <button type="button" className="toggle" aria-expanded={more} onClick={() => setMore(!more)}>
              {more ? "접기" : `펼치기 · ${rows.length}위까지`}
            </button>
          ) : null}
          <p className="note">
            진입한 주 = 기간 중 뜨는 축 AI 탭에 든 주 수(칸마다 한 주, 오래된 주 → 이번 주). 연속 = 이번 주까지 끊기지 않고 든 주 수.
            숫자는 공개 주간 스타 파일로 코드가 계산한다.
          </p>
        </section>
        {footer}
      </main>
    </>
  );
}
