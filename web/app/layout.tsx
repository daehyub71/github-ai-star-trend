import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans_KR } from "next/font/google";

import "./globals.css";

// 글꼴 — 시안 v1.1: 본문 IBM Plex Sans KR · 숫자·저장소 이름 IBM Plex Mono
const sans = IBM_Plex_Sans_KR({ weight: ["400", "500", "600", "700"], variable: "--font-sans", preload: false });
const mono = IBM_Plex_Mono({ weight: ["400", "500", "600"], subsets: ["latin"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "GitHub AI 스타 트렌드",
  description: "GitHub 주간 스타 변화로 본 AI 저장소 흐름 — 개인용 비공개 사이트",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" className={`${sans.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
