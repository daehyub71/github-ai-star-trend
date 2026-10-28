// 이번 주 화면의 랭킹 카드 4개 — 시안 v1.1(DESIGN §6): 축 순서·정의·값·칩. v1.3: 카드 배지·'왜 지금' 한 줄·카테고리 색
import { fmtInt, fmtSigned, isFresh, mmdd, splitName } from "./format";
import type { Axis, Entry, WeekData } from "./types";

export type ChipKind = "cat" | "no" | "pending" | "flag" | "fresh" | "type" | "card";
export type Chip = { kind: ChipKind; label: string; catId?: string };

export type Row = {
  key: string;
  owner: string;
  repo: string;
  fullName: string;
  desc: string;
  chips: Chip[];
  value: string;
  sub: string;
  href: string;
  hasCard: boolean;
  why: string;
};

export type Section = {
  key: Axis;
  title: string;
  def: string;
  note: string;
  all: Row[];
  ai: Row[] | null;
};

const DEFS: { key: Axis; title: string; def: string; note: string }[] = [
  { key: "gain", title: "지금 뜨는 저장소", def: "지난 주 받은 스타", note: "" },
  { key: "fresh", title: "새로 뜨는 저장소", def: "생성 30일 이내 · 누적 스타 순", note: "" },
  { key: "growth", title: "규모 대비 급성장", def: "지난 주 증가 ÷ 주 시작 스타 · 주 시작 1,000 이상", note: "" },
  { key: "total", title: "누적 스타 TOP", def: "전체 기간", note: "전체 탭 상위는 교육자료·목록이 많다 — 유형 라벨로 도구와 구분한다" },
];

const TOOL = "도구/라이브러리";

export function slugOf(fullName: string): string {
  return fullName.replace("/", "__");
}

function chips(e: Entry, axis: Axis, weekEnd: string, names: Record<string, string>): Chip[] {
  const out: Chip[] = [];
  if (e.is_ai === true) {
    out.push(e.category ? { kind: "cat", label: names[e.category] ?? e.category, catId: e.category }
      : { kind: "cat", label: "AI" });
  }
  else if (e.is_ai === false) out.push({ kind: "no", label: "AI 아님" });
  else out.push({ kind: "pending", label: "분류 전" });
  if (e.type && e.type !== TOOL) out.push({ kind: "type", label: e.type });
  if (axis !== "fresh" && e.created && isFresh(e.created, weekEnd)) out.push({ kind: "fresh", label: "30일 이내" });
  for (const f of e.flags ?? []) out.push({ kind: "flag", label: f.label });
  return out;
}

function rankMove(e: Entry): string {
  if (e.prev_rank == null) return "새로 진입";
  const d = e.prev_rank - e.rank;
  const arrow = d > 0 ? `▲ ${d}` : d < 0 ? `▼ ${-d}` : "–";
  return `${arrow} (지난 주 ${e.prev_rank}위)`;
}

function valueOf(e: Entry, axis: Axis): { value: string; sub: string } {
  switch (axis) {
    case "gain":
      return { value: fmtSigned(e.gain), sub: `누적 ${fmtInt(e.stars_end)}` };
    case "fresh":
      return { value: fmtInt(e.stars_end), sub: `생성 ${mmdd(e.created)}` };
    case "growth":
      return {
        value: e.growth == null ? "—" : `+${(e.growth * 100).toFixed(1)}%`,
        sub: `${fmtInt(e.start_stars)} → ${fmtInt(e.stars_end)}`,
      };
    case "total":
      return { value: fmtInt(e.stars_end), sub: rankMove(e) };
  }
}

/** cards — 카드가 있는 저장소의 slug → 카드 ① '왜 지금 떴나' 한 줄 */
function toRow(e: Entry, axis: Axis, weekEnd: string, names: Record<string, string>, cards: Map<string, string>): Row {
  const { owner, repo } = splitName(e.full_name);
  const slug = slugOf(e.full_name);
  const hasCard = cards.has(slug);
  const base = chips(e, axis, weekEnd, names);
  return {
    key: `${axis}-${e.id}`, owner, repo, fullName: e.full_name, desc: e.description || "설명 없음",
    chips: hasCard ? [...base, { kind: "card", label: "카드" }] : base, ...valueOf(e, axis),
    href: hasCard ? `/repo/${e.full_name}` : `https://github.com/${e.full_name}`,
    hasCard, why: cards.get(slug) ?? "",
  };
}

export function buildSections(week: WeekData, names: Record<string, string>, cards: Map<string, string>): Section[] {
  return DEFS.map((d) => {
    const tabs = week.axes[d.key] ?? { all: [], ai: null };
    const rows = (list: Entry[]) => list.map((e) => toRow(e, d.key, week.week_end, names, cards));
    return { ...d, all: rows(tabs.all), ai: tabs.ai == null ? null : rows(tabs.ai) };
  });
}

/** 오른쪽 막대 — AI 탭 "지금 뜨는" 15개 중 카테고리별 개수 */
export function catBars(week: WeekData, names: Record<string, string>): { id: string; label: string; count: number; width: string }[] {
  const counts = new Map<string, number>();
  for (const e of week.axes.gain?.ai ?? []) {
    if (e.category) counts.set(e.category, (counts.get(e.category) ?? 0) + 1);
  }
  const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const max = sorted[0]?.[1] ?? 1;
  return sorted.map(([id, n]) => ({ id, label: names[id] ?? id, count: n, width: `${(n / max) * 100}%` }));
}

/** 브리핑이 없는 주 — 코드가 계산한 사실만으로 쓴 헤드라인과 세 줄 */
export function codeFacts(week: WeekData, names: Record<string, string>): { headline: string; items: string[] } {
  const top = week.axes.gain?.ai?.[0] ?? week.axes.gain?.all?.[0];
  const growth = week.axes.growth?.ai?.[0];
  const fresh = week.axes.fresh?.ai?.[0];
  const headline = top
    ? `지난 주 가장 많은 스타를 받은 AI 저장소는 ${top.full_name}(${fmtSigned(top.gain)})였다`
    : "이번 주 랭킹이 아직 없다";
  const items: string[] = [];
  if (growth) items.push(`${growth.full_name} — 규모 대비 성장률 1위(+${((growth.growth ?? 0) * 100).toFixed(1)}%).`);
  if (fresh) items.push(`${fresh.full_name} — 생성 30일 이내 저장소 중 누적 스타 1위(${fmtInt(fresh.stars_end)}).`);
  const cat = catBars(week, names)[0];
  if (cat) items.push(`AI 탭 "지금 뜨는" 15개 중 ${cat.label} 이 ${cat.count}개로 가장 많다.`);
  return { headline, items };
}

/** 히어로 숫자 타일 3개 — AI 탭 최다 증가 · 최고 성장률 · 이번 주 AI 저장소 수(4축 중복 제외)와 카드 수 */
export function heroStats(week: WeekData, cardCount: number): { value: string; label: string }[] {
  const top = week.axes.gain?.ai?.[0];
  const growth = week.axes.growth?.ai?.[0];
  const ids = new Set<number>();
  for (const tabs of Object.values(week.axes)) for (const e of tabs?.ai ?? []) ids.add(e.id);
  const short = (name: string) => splitName(name).repo;
  return [
    { value: top ? fmtSigned(top.gain) : "—", label: top ? `최다 증가 · ${short(top.full_name)}` : "최다 증가" },
    { value: growth?.growth != null ? `${Math.round(growth.growth * 100).toLocaleString("en-US")}%` : "—",
      label: growth ? `최고 성장률 · ${short(growth.full_name)}` : "최고 성장률" },
    { value: fmtInt(ids.size), label: `이번 주 AI 저장소 · 카드 ${cardCount}장` },
  ];
}
