// data/site/ 파생 데이터의 모양 (startrend/stages/export.py 와 짝) — FR-9

export type Flag = { kind: string; label: string; value: number };

export type Entry = {
  id: number;
  full_name: string;
  description: string;
  language: string | null;
  created: string;
  stars_end: number;
  gain: number;
  growth: number | null;
  start_stars: number | null;
  rank: number;
  prev_rank: number | null;
  is_ai: boolean | null;
  type: string | null;
  category: string | null;
  secondary: string | null;
  flags: Flag[] | null;
  exact: boolean | null;
  days: number[] | null;
  spark: number[];
};

export type Axis = "gain" | "fresh" | "growth" | "total";
export type Tabs = { all: Entry[]; ai: Entry[] | null };

export type WeekData = {
  week: string;
  week_end: string;
  axes: Partial<Record<Axis, Tabs>>;
  ai_status: Record<string, { found: number; pending_above: number }> | null;
};

export type SiteIndex = {
  weeks: string[];
  latest: string | null;
  taxonomy_version: number | null;
  types: string[];
  categories: { id: string; name: string }[];
};

export type Series = { gain: (number | null)[]; repos: (number | null)[]; entrants: (number | null)[] };

export type Categories = {
  weeks: string[];
  series: Record<string, Series>;
  coverage: (number | null)[];
  names: Record<string, string>;
};

export type CardRef = { repo_id: number; full_name: string; as_of: string | null; slug: string };

/** repos.json — 저장소 추이(시안 v1.3). bits 는 weeks 와 같은 길이, 오래된 주 → 이번 주 */
export type RepoTrend = {
  id: number;
  full_name: string;
  category: string | null;
  bits: string;
  streak: number;
  gain4: number;
  spark: number[];
};

export type RepoTrends = { weeks: string[]; axes: string[]; repos: RepoTrend[] };
