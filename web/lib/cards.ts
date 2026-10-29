// '이번 주 카드' 목록 — 시안 v1.3. 이번 주 AI 탭(4축)에 든 저장소 중 카드가 있는 것, 축 순서·순위 순
import { splitName } from "./format";
import type { CardBrief } from "./markdown";
import { slugOf } from "./rankings";
import type { Axis, WeekData } from "./types";

export type WeekCard = CardBrief & {
  slug: string;
  fullName: string;
  owner: string;
  repo: string;
  catId: string | null;
  catName: string;
  href: string;
};

const ORDER: Axis[] = ["gain", "growth", "fresh", "total"];

/** 그 주 화면(랭킹 전체·AI 탭)에 나오는 저장소의 slug — 이 카드만 읽는다(P4-4) */
export function cardSlugsForWeek(week: WeekData): Set<string> {
  const out = new Set<string>();
  for (const tabs of Object.values(week.axes)) {
    for (const e of [...(tabs?.all ?? []), ...(tabs?.ai ?? [])]) out.add(slugOf(e.full_name));
  }
  return out;
}

export function weekCardList(week: WeekData, briefs: Map<string, CardBrief>,
  names: Record<string, string>): WeekCard[] {
  const out: WeekCard[] = [];
  const seen = new Set<string>();
  for (const axis of ORDER) {
    for (const e of week.axes[axis]?.ai ?? []) {
      const slug = slugOf(e.full_name);
      const brief = briefs.get(slug);
      if (!brief || seen.has(slug)) continue;
      seen.add(slug);
      out.push({
        ...brief, slug, fullName: e.full_name, ...splitName(e.full_name), catId: e.category,
        catName: e.category ? names[e.category] ?? e.category : "AI", href: `/repo/${e.full_name}`,
      });
    }
  }
  return out;
}
