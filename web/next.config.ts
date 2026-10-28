import type { NextConfig } from "next";

// 데이터는 빌드 때 서버 컴포넌트에서만 읽는다(NFR-6) — 클라이언트 번들에는 화면에 필요한 행만 간다.
const config: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
};

export default config;
