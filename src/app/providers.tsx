'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import type { ColorScheme } from '@coinbase/cds-common';
import { ThemeProvider } from '@coinbase/cds-web';
import { PortalProvider } from '@coinbase/cds-web/overlays';
import { MediaQueryProvider } from '@coinbase/cds-web/system';

import { sauronTheme } from '@/theme/sauronTheme';

type SchemeContextValue = { scheme: ColorScheme; toggleScheme: () => void };
const SchemeContext = createContext<SchemeContextValue | undefined>(undefined);

export function useScheme(): SchemeContextValue {
  const ctx = useContext(SchemeContext);
  if (!ctx) throw new Error('useScheme must be used inside <Providers>');
  return ctx;
}

/**
 * THE app root. `ThemeProvider` 하나, 중첩 금지 — 두 개면 팔레트가 갈라지고
 * 그 순간 어떤 대비 측정도 «지금 보는 화면» 에 대한 말이 아니게 된다. (v2 규율 그대로)
 *
 * `data-sr-scheme` 은 방향색(`theme/direction.css`)이 물 자리다. CDS 는 팔레트를
 * 인라인 CSS 변수로 뱉고 걸 수 있는 클래스·속성을 주지 않아서, 이 하나만 우리가 갖는다.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  /** 화면 밝기는 «질문» 이 아니라 «이 사람이 이 화면을 보는 조건» 이다 —
   *  창을 닫았다 열 때마다 다시 고르게 하는 것은 설정을 안 지키는 것이다. */
  const [scheme, setScheme] = useState<ColorScheme>('light');

  useEffect(() => {
    try {
      const saved = localStorage.getItem('kbond.scheme');
      if (saved === 'dark' || saved === 'light') setScheme(saved);
    } catch {
      /* 사생활 모드 등 — 기본값으로 간다 */
    }
  }, []);

  /* html 에도 남긴다 — `color-scheme` 은 UA 힌트라 **문서 뿌리**에 있어야
   * 브라우저 크롬(스크롤바·네이티브 입력)이 따라온다. 리터럴 hex 로 된
   * `--sr-up`/`--sr-down` 다크 쌍도 여기서 풀린다. */
  useEffect(() => {
    document.documentElement.setAttribute('data-sr-scheme', scheme);
    try {
      localStorage.setItem('kbond.scheme', scheme);
    } catch {
      /* 저장 못 해도 화면은 돈다 */
    }
  }, [scheme]);

  const toggleScheme = useCallback(
    () => setScheme((s) => (s === 'light' ? 'dark' : 'light')),
    [],
  );
  const value = useMemo(() => ({ scheme, toggleScheme }), [scheme, toggleScheme]);

  return (
    <MediaQueryProvider>
      <ThemeProvider theme={sauronTheme} activeColorScheme={scheme}>
        <PortalProvider>
          {/* ★2026-09-04 수리: 이 래퍼가 없으면 `direction.css` 의 `[data-sr-scheme]`
              별칭 블록이 통째로 죽는다. CDS 는 `--color-*` 를 **자기 ThemeProvider
              래퍼에 인라인으로** 심고, 커스텀 속성은 «선언된 자리» 에서 치환된다.
              그래서 html(조상)에 선언하면 `--sr-card: var(--color-bg)` 가 «없음» 으로
              풀린다 — 실측 2026-09-04: 카드 위치에서 `--sr-card` 가 빈 값이었다.
              `direction.css` 주석이 말한 «ThemeProvider 의 자식 div» 가 이것이다.
              `display: contents` 라 상자를 만들지 않아 배치에는 영향이 없다. */}
          <div className="kb-scheme-root" data-sr-scheme={scheme}>
            <SchemeContext.Provider value={value}>{children}</SchemeContext.Provider>
          </div>
        </PortalProvider>
      </ThemeProvider>
    </MediaQueryProvider>
  );
}
