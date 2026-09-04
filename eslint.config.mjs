// Next.js 기본 규칙 + 이 앱의 규율 둘.
//
// ★설치가 없어 `pnpm lint` 가 여태 실행조차 안 됐다(스크립트만 있었다).
//   [OWNER 2026-09-04 「설치하고 설정 넣기」]
import { FlatCompat } from '@eslint/eslintrc';

const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

export default [
  { ignores: ['.next/**', 'node_modules/**', 'src/lib/api-types.d.ts'] },
  ...compat.extends('next/core-web-vitals', 'next/typescript'),
  {
    rules: {
      // 훅 의존성은 이 앱에서 실제로 물린 적이 있다(피드 SSE) — 경고로 둔다.
      'react-hooks/exhaustive-deps': 'warn',
    },
  },
];
