import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Markdown } from "@/components/Markdown";
import { SiteFooter, SiteHeader } from "@/components/SiteHeader";
import { briefingWeeks, loadBriefing } from "@/lib/data";
import { parseBriefing } from "@/lib/markdown";

// 주간 브리핑 전체 — 비공개 사본이 있는 주만(결정 53)
export const dynamicParams = false;

export function generateStaticParams() {
  return briefingWeeks().map((week) => ({ week }));
}

export async function generateMetadata({ params }: { params: Promise<{ week: string }> }): Promise<Metadata> {
  const { week } = await params;
  return { title: `${week} 주 브리핑 — GitHub AI 스타 트렌드` };
}

export default async function BriefingPage({ params }: { params: Promise<{ week: string }> }) {
  const { week } = await params;
  const raw = loadBriefing(week);
  if (!raw) notFound();
  const b = parseBriefing(raw);
  return (
    <>
      <SiteHeader current="week" />
      <main className="page">
        <nav aria-label="위치" className="crumbs"><Link href={`/week/${week}`}>{week} 주</Link> › 주간 브리핑</nav>
        <article className="panel">
          <h1 style={{ margin: 0, fontSize: "clamp(22px, 2.6vw, 30px)", letterSpacing: "-0.4px" }}>{b.title}</h1>
          <Markdown>{b.body}</Markdown>
          <p className="muted small">
            기준일 {b.front.as_of ?? "—"} · 인용 게이트 검사 {b.front.gate_checked ?? "—"} · 제외 {b.front.gate_excluded ?? "—"}
          </p>
        </article>
        <SiteFooter asOf={b.front.as_of} />
      </main>
    </>
  );
}
