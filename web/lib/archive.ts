// 주간 아카이브 — 시안 v1.4. 주마다 한 줄 요약(AI 1위 · AI 저장소 수 · 많은 카테고리 · 새로 뜬 1위 · 브리핑 여부)
import type { WeekData } from "./types";

export type ArchiveRow = {
  week: string;
  end: string;
  top: string | null;
  gain: number;
  topCat: string | null;
  n: number;
  lead: string | null;
  fresh: string | null;
  brief: boolean;
};

export function archiveRow(w: WeekData, brief: boolean): ArchiveRow {
  const gainAi = w.axes.gain?.ai ?? [];
  const top = gainAi[0] ?? null;
  const ids = new Set<number>();
  for (const tabs of Object.values(w.axes)) for (const e of tabs?.ai ?? []) ids.add(e.id);
  // 많은 카테고리 — AI 탭 "지금 뜨는" 안에서 개수, 같으면 먼저 나온 것
  const counts = new Map<string, number>();
  for (const e of gainAi) if (e.category) counts.set(e.category, (counts.get(e.category) ?? 0) + 1);
  let lead: string | null = null;
  for (const [cat, n] of counts) if (lead === null || n > (counts.get(lead) ?? 0)) lead = cat;
  return {
    week: w.week, end: w.week_end, top: top?.full_name ?? null, gain: top?.gain ?? 0,
    topCat: top?.category ?? null, n: ids.size, lead, fresh: w.axes.fresh?.ai?.[0]?.full_name ?? null, brief,
  };
}

export type MonthGroup = { key: string; label: string; rows: ArchiveRow[] };

/** 주 시작일의 달로 묶는다 — 최신 주가 먼저 */
export function monthGroups(rows: ArchiveRow[]): MonthGroup[] {
  const out: MonthGroup[] = [];
  for (const r of [...rows].sort((a, b) => b.week.localeCompare(a.week))) {
    const key = r.week.slice(0, 7);
    let g = out.at(-1);
    if (!g || g.key !== key) {
      g = { key, label: `${key.slice(0, 4)}년 ${Number(key.slice(5, 7))}월`, rows: [] };
      out.push(g);
    }
    g.rows.push(r);
  }
  return out;
}

/** 막대 아래 달 라벨 — 달이 바뀌는 주에만. 첫 주와 1월은 "26.01" 처럼 연도를 붙인다.
 *  앞 라벨과 바로 붙는 칸이면 생략한다(칸 하나에 다 들어가지 않아 겹친다) */
export function monthLabels(weeks: string[]): string[] {
  let last = -2;
  return weeks.map((w, i) => {
    const m = w.slice(5, 7);
    if ((i > 0 && weeks[i - 1].slice(5, 7) === m) || i - last < 2) return "";
    last = i;
    return i === 0 || m === "01" ? `${w.slice(2, 4)}.${m}` : m;
  });
}

/** 막대 높이(px) — 제곱근 눈금. 큰 주 하나가 나머지를 납작하게 만들지 않게. 0 도 3px 은 보인다 */
export function barHeights(values: number[], maxPx: number): number[] {
  const max = Math.max(1, ...values);
  return values.map((v) => Math.max(3, Math.round(Math.sqrt(Math.max(0, v) / max) * maxPx)));
}
