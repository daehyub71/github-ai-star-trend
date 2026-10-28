import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { CardView } from "@/components/CardView";
import { loadCard, loadCardIndex } from "@/lib/data";

// 카드가 있는 저장소만 페이지를 만든다(NFR-6) — 카드는 비공개 사본에서(결정 53)
export const dynamicParams = false;

export function generateStaticParams() {
  return loadCardIndex().map((c) => {
    const [owner, name] = c.full_name.split("/");
    return { owner, name };
  });
}

type Params = Promise<{ owner: string; name: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { owner, name } = await params;
  return { title: `${owner}/${name} — GitHub AI 스타 트렌드` };
}

export default async function RepoPage({ params }: { params: Params }) {
  const { owner, name } = await params;
  const ref = loadCardIndex().find((c) => c.full_name.toLowerCase() === `${owner}/${name}`.toLowerCase());
  const md = ref ? loadCard(ref.slug) : null;
  if (!ref || !md) notFound();
  return <CardView markdown={md} fullName={ref.full_name} />;
}
