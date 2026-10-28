import type { Metadata } from "next";

import { SiteFooter, SiteHeader } from "@/components/SiteHeader";
import { TrendsChart } from "@/components/TrendsChart";
import { loadCategories, loadIndex, loadWeek } from "@/lib/data";
import { fmtInt, fmtPct } from "@/lib/format";
import { trendRows } from "@/lib/trends";

export const metadata: Metadata = { title: "카테고리 추이 — GitHub AI 스타 트렌드" };

// 카테고리 추이 — 시안 v1.1: 선 그래프 + 카테고리별 이번 주 표 (FR-8.1 — 집계 범위를 함께 적는다)
export default function TrendsPage() {
  const cats = loadCategories();
  const index = loadIndex();
  const latest = index.latest ? loadWeek(index.latest) : null;
  const rows = trendRows(cats, latest);
  const initial = ["ALL", ...rows.slice(0, 4).map((r) => r.id)];
  const cov = cats.coverage[cats.coverage.length - 1];

  return (
    <>
      <SiteHeader current="trends" />
      <main className="page">
        <div className="week-head">
          <div className="when">
            <h1 style={{ margin: 0, fontSize: "clamp(22px, 2.6vw, 28px)", letterSpacing: "-0.3px" }}>카테고리 추이</h1>
            <span className="muted">카테고리별 주간 스타 증가 합계 · UTC 일~토 · {cats.weeks.length}주</span>
          </div>
        </div>
        <TrendsChart cats={cats} initial={initial} />
        <p className="banner">
          집계 범위: 판정된 저장소(랭킹 후보 쪽)의 증가만 셉니다 — 최근 주 커버리지 {fmtPct(cov ?? null, 0)}.
          GitHub 전체의 AI 지형이 아니라 랭킹에 오르는 쪽의 구성입니다. ALL 은 모든 AI 카테고리의 합계입니다.
        </p>
        <section className="panel">
          <div className="panel-head">
            <h2>카테고리별 이번 주</h2>
            <span className="muted small">AI 탭 진입 = 이번 주 AI 탭 4축에 든 저장소 수 · 대표 저장소 = AI 탭 &quot;지금 뜨는&quot; 순</span>
          </div>
          <div className="table-wrap">
            <table style={{ minWidth: 640 }}>
              <thead>
                <tr>
                  <th scope="col">카테고리</th>
                  <th scope="col" className="num">주간 증가</th>
                  <th scope="col" className="num">앞 4주 평균 대비</th>
                  <th scope="col" className="num">AI 탭 진입</th>
                  <th scope="col">대표 저장소</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <th scope="row" style={{ whiteSpace: "nowrap" }}>{r.label}</th>
                    <td className="num">{fmtInt(r.gain)}</td>
                    <td className="num">{r.vsAvg == null ? "—" : `${r.vsAvg >= 0 ? "+" : ""}${(r.vsAvg * 100).toFixed(0)}%`}</td>
                    <td className="num">{fmtInt(r.entrants)}</td>
                    <td className="mono" style={{ fontSize: 13 }}>{r.repos.join(" · ") || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <SiteFooter asOf={latest?.week_end} />
      </main>
    </>
  );
}
