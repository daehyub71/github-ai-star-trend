// 저장소 추이 — 시안 v1.3 "꾸준히 뜨는 저장소". 기간(12·52주) 안에서 뜨는 축 AI 탭에 든 주를 센다
import { splitName } from "./format";
import { slugOf } from "./rankings";
import type { RepoTrends } from "./types";

export type Period = 12 | 52;
export type SortKey = "weeks" | "gain" | "streak";

export type TrendRow = {
  rank: number;
  fullName: string;
  owner: string;
  repo: string;
  catId: string | null;
  weeks: number;
  bits: string;
  streak: number;
  gain4: number;
  spark: number[];
  hasCard: boolean;
  href: string;
};

export function repoView(data: RepoTrends, period: Period, sort: SortKey, limit: number,
  cards: Set<string>): TrendRow[] {
  const rows = data.repos.map((r) => {
    const bits = r.bits.slice(-period);
    const slug = slugOf(r.full_name);
    return {
      rank: 0, fullName: r.full_name, ...splitName(r.full_name), catId: r.category,
      weeks: bits.split("").filter((b) => b === "1").length, bits, streak: r.streak, gain4: r.gain4,
      spark: r.spark, hasCard: cards.has(slug),
      href: cards.has(slug) ? `/repo/${r.full_name}` : `https://github.com/${r.full_name}`,
    };
  }).filter((r) => r.weeks > 0);
  const key = (r: TrendRow): [number, number] =>
    sort === "weeks" ? [r.weeks, r.gain4] : sort === "gain" ? [r.gain4, r.weeks] : [r.streak, r.gain4];
  rows.sort((a, b) => {
    const [a1, a2] = key(a);
    const [b1, b2] = key(b);
    return b1 - a1 || b2 - a2 || a.fullName.localeCompare(b.fullName);
  });
  return rows.slice(0, limit).map((r, i) => ({ ...r, rank: i + 1 }));
}
