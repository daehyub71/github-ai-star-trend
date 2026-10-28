// 카테고리 추이 화면 — 그래프 점과 표 행 (FR-8.1). 숫자는 export 가 미리 집계한 categories.json 에서만
import { mmdd } from "./format";
import type { Categories, WeekData } from "./types";

export const MAX_SELECTED = 6;          // 시안: ALL 포함 최대 6개
export const PERIODS = [12, 52] as const;

export type Point = { week: string } & Record<string, number | string | null>;

export function chartData(cats: Categories, selected: string[], period: number): Point[] {
  const start = Math.max(0, cats.weeks.length - period);
  return cats.weeks.slice(start).map((w, i) => {
    const p: Point = { week: mmdd(w) };
    for (const id of selected) p[id] = cats.series[id]?.gain[start + i] ?? null;
    return p;
  });
}

export type TrendRow = {
  id: string;
  label: string;
  gain: number | null;
  vsAvg: number | null;        // 이번 주 ÷ 앞 4주 평균 − 1
  entrants: number | null;
  repos: string[];             // AI 탭 "지금 뜨는" 순서로 앞 2개
};

export function trendRows(cats: Categories, latest: WeekData | null): TrendRow[] {
  const last = cats.weeks.length - 1;
  const rows: TrendRow[] = [];
  for (const [id, s] of Object.entries(cats.series)) {
    if (id === "ALL" || last < 0) continue;
    const prev = s.gain.slice(Math.max(0, last - 4), last).filter((v): v is number => v != null);
    const avg = prev.length ? prev.reduce((a, b) => a + b, 0) / prev.length : null;
    const now = s.gain[last];
    const repos = (latest?.axes.gain?.ai ?? []).filter((e) => e.category === id).slice(0, 2).map((e) => e.full_name);
    rows.push({
      id, label: cats.names[id] ?? id, gain: now, entrants: s.entrants[last], repos,
      vsAvg: now != null && avg ? now / avg - 1 : null,
    });
  }
  return rows.sort((a, b) => (b.gain ?? -1) - (a.gain ?? -1) || a.id.localeCompare(b.id));
}
