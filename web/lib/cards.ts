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
