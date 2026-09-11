import type { NextConfig } from "next";

/** 정적 내보내기 — v2 와 달리 이 앱에는 서버 라우트가 없다.
 *  데이터는 «보는 사람 브라우저» 가 로컬 백엔드(Funnel)로 직접 부른다.
 *  그래서 Vercel 은 파일만 배달하면 되고, 배포가 단순해진다(안정성). */
/** ★[2026-09-11] 한 벌을 두 자리에 낸다.
 *
 *  Vercel 은 루트에 배달한다(접두어 없음). 오너 PC 는 같은 화면을 Funnel 의
 *  `/kbond/app` 에도 낸다 — 주소를 하나로 쓰기 위해서다. Tailscale 이 `/kbond` 를
 *  떼고 백엔드로 넘기므로, 자산 주소가 «절대 경로»면 루트(다른 앱)로 새 나간다.
 *  그래서 접두어 빌드를 따로 굽는다:  KBOND_BASE_PATH=/kbond/app npm run build
 *  (`build_app.ps1` 이 그 빌드를 `out-kbond` 로 옮긴다.)
 */
const BASE = process.env.KBOND_BASE_PATH || "";

const nextConfig: NextConfig = {
  output: "export",
  ...(BASE ? { basePath: BASE, assetPrefix: BASE } : {}),
  images: { unoptimized: true },
  transpilePackages: ["@coinbase/cds-web", "@coinbase/cds-common", "@coinbase/cds-icons"],
};

export default nextConfig;
