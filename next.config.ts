import type { NextConfig } from "next";

/** 정적 내보내기 — v2 와 달리 이 앱에는 서버 라우트가 없다.
 *  데이터는 «보는 사람 브라우저» 가 로컬 백엔드(Funnel)로 직접 부른다.
 *  그래서 Vercel 은 파일만 배달하면 되고, 배포가 단순해진다(안정성). */
const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  transpilePackages: ["@coinbase/cds-web", "@coinbase/cds-common", "@coinbase/cds-icons"],
};

export default nextConfig;
