import type { Metadata } from "next";

import { RepoTrends } from "@/components/RepoTrends";
import { SiteFooter, SiteHeader } from "@/components/SiteHeader";
import { artUrl } from "@/lib/art";
import { loadCardIndex, loadIndex, loadRepos } from "@/lib/data";
import { repoView, type Period, type SortKey, type TrendRow } from "@/lib/repotrends";

export const metadata: Metadata = { title: "저장소 추이 — GitHub AI 스타 트렌드" };

const LIMIT = 30;

// 저장소 추이 — 시안 v1.3: 카테고리 추이 대신 "꾸준히 뜨는 저장소" 목록(사용자 결정 2026-10-28)
export default function TrendsPage() {
  const data = loadRepos();
  const index = loadIndex();
  const names = Object.fromEntries(index.categories.map((c) => [c.id, c.name]));
  const cards = new Set(loadCardIndex().map((c) => c.slug));
  const views: Record<string, TrendRow[]> = {};
  for (const p of [12, 52] as Period[]) {
    for (const s of ["weeks", "gain", "streak"] as SortKey[]) views[`${p}-${s}`] = repoView(data, p, s, LIMIT, cards);
  }
  const art = artUrl("hero-trends");
  return (
    <div className="trends-page" style={art ? { ["--trends-art" as string]: `url(${art})` } : undefined}>
      <RepoTrends views={views} names={names} until={data.weeks.at(-1) ?? "—"}
        header={<SiteHeader current="trends" />} footer={<SiteFooter />} />
    </div>
  );
}
