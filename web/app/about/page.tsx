import type { Metadata } from "next";

import { AboutContent } from "@/components/AboutContent";
import { SiteFooter, SiteHeader } from "@/components/SiteHeader";

export const metadata: Metadata = { title: "소개·방법론 — GitHub AI 스타 트렌드" };

// 소개·방법론 — 시안 v1.4 · NFR-11. 데이터를 읽지 않는 고정 페이지
export default function AboutPage() {
  return (
    <>
      <div className="top top-about">
        <SiteHeader current="about" />
        <section className="hero column-hero" aria-labelledby="about-title">
          <span className="pill teal"><span className="live" />소개·방법론</span>
          <h1 id="about-title">무엇을, <span className="grad-text">어떻게</span> 재나</h1>
          <p className="lede">GitHub 저장소가 매주 받은 스타로 AI 개발 흐름을 읽는 개인 프로젝트입니다. <b>숫자는 GitHub API 값을 코드가 계산하고</b>, 카드와 브리핑은 <b>AI(Claude)가 근거를 붙여 씁니다.</b></p>
          <div className="stats">
            <div className="stat"><span className="v v2">월 09:00 KST</span><span className="l">매주 지난 주(UTC 일~토)를 정리</span></div>
            <div className="stat"><span className="v v0">약 6.6만 개</span><span className="l">매주 스냅샷하는 스타 1,000+ 저장소</span></div>
            <div className="stat"><span className="v v1">96.7%</span><span className="l">AI 판정 정확도 — 사람 라벨 블라인드 60개</span></div>
            <div className="stat"><span className="v v2">주장마다 출처</span><span className="l">근거 목록에 없는 링크는 코드가 뺀다</span></div>
          </div>
        </section>
      </div>
      <main className="page overlap">
        <AboutContent />
        <SiteFooter />
      </main>
    </>
  );
}
