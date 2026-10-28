import type { Metadata } from "next";

import { WeekView } from "@/components/WeekView";
import { loadIndex } from "@/lib/data";

export const dynamicParams = false;

export function generateStaticParams() {
  return loadIndex().weeks.map((week) => ({ week }));
}

export async function generateMetadata({ params }: { params: Promise<{ week: string }> }): Promise<Metadata> {
  const { week } = await params;
  return { title: `${week} 주 — GitHub AI 스타 트렌드` };
}

export default async function WeekPage({ params }: { params: Promise<{ week: string }> }) {
  const { week } = await params;
  return <WeekView week={week} />;
}
