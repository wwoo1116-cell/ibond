import type { Metadata } from 'next';

import '@coinbase/cds-icons/fonts/web/icon-font.css';
import '@coinbase/cds-web/defaultFontStyles';
import '@coinbase/cds-web/globalStyles';

import '@/theme/direction.css';
import '@/theme/motion.css';
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
