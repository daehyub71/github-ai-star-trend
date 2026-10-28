// 머리 — 시안 v1.1. 주간 아카이브·소개·방법론은 시안 합의(P4-11) 뒤에 넣는다
import Link from "next/link";

export function SiteHeader({ current }: { current: "week" | "trends" | "card" }) {
  return (
    <header className="site-header">
      <div className="inner">
        <Link className="brand" href="/">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#1F5BD8" strokeWidth="2"
            strokeLinejoin="round" aria-hidden="true">
            <path d="M12 3l2.6 5.6 6.1.7-4.5 4.2 1.2 6L12 16.6 6.6 19.5l1.2-6L3.3 9.3l6.1-.7z" />
          </svg>
          <span>GitHub AI 스타 트렌드</span>
        </Link>
        <nav aria-label="주요 화면" className="site-nav">
          <Link href="/" aria-current={current === "week" ? "page" : undefined}>이번 주</Link>
          <Link href="/trends" aria-current={current === "trends" ? "page" : undefined}>카테고리 추이</Link>
        </nav>
      </div>
    </header>
  );
}

export function SiteFooter({ asOf }: { asOf?: string }) {
  return (
    <footer className="site-footer">
      <span>트렌드 지표는 GitHub 공식 지표가 아닌 자체 산출값입니다 · 데이터: GitHub API{asOf ? ` · 기준 ${asOf}` : ""}</span>
      <span>스타 ≠ 사용량 · 급등 패턴은 표시만 합니다</span>
    </footer>
  );
}
