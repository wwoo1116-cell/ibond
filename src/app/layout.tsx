import type { Metadata } from 'next';

/* ★[2026-09-28 경량화] 아이콘 글꼴(273KB)은 뺐다 — 이 앱은 CDS 아이콘을 한 곳도 안 쓴다
 * (src 전체에 Icon 컴포넌트 0). 쓰게 되면 `@coinbase/cds-icons/fonts/web/icon-font.css` 를 되살린다. */
import '@coinbase/cds-web/defaultFontStyles';
import '@coinbase/cds-web/globalStyles';

import '@/theme/direction.css';
import '@/theme/motion.css';
import '@/theme/pretendard-dyn.css';
import '@/theme/type.css';
import '@/theme/kbond.css';

import { Providers } from './providers';

export const metadata: Metadata = {
  title: 'K-Bond 라이브 호가창',
  description: '장외 채권 메신저 호가를 접은 책',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
