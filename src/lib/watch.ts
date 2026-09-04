'use client';

/**
 * 관심 종목(☆) — 이 브라우저에만 남는다.
 *
 * ★서버로 안 보낸다. 누가 무엇을 보고 있는지는 그 사람 것이고, 이 앱에는 사람을
 *   구분할 계정이 없다. localStorage 로 충분하고, 없으면 그냥 빈 목록으로 돈다.
 *
 * ★키는 종목 코드다(없으면 표시명). 옛 화면의 `watch` 집합과 같은 자리다.
 */
import { useCallback, useEffect, useState } from 'react';

const KEY = 'kbond.watch';

function read(): Set<string> {
  try {
    const raw = localStorage.getItem(KEY);
    return new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set(); /* 사생활 모드 등 — 빈 목록으로 간다 */
  }
}

/** 창이 여럿이어도 같은 목록을 보게 한다(storage 이벤트는 다른 탭에서만 온다). */
const subs = new Set<(s: Set<string>) => void>();

export function useWatch() {
  const [watch, setWatch] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    setWatch(read());
    const onSelf = (s: Set<string>) => setWatch(new Set(s));
    subs.add(onSelf);
    const onOther = (e: StorageEvent) => {
      if (e.key === KEY) setWatch(read());
    };
    window.addEventListener('storage', onOther);
    return () => {
      subs.delete(onSelf);
      window.removeEventListener('storage', onOther);
    };
  }, []);

  const toggle = useCallback((k?: string | null) => {
    if (!k) return;
    const next = read();
    if (next.has(k)) next.delete(k);
    else next.add(k);
    try {
      localStorage.setItem(KEY, JSON.stringify([...next]));
    } catch {
      /* 저장 못 해도 이번 세션은 돈다 */
    }
    for (const fn of subs) fn(next);
  }, []);

  return { watch, toggle };
}

/** 피드 행에서 관심 키를 뽑는다 — 코드가 있으면 코드, 없으면 표시명. */
export const watchKey = (e: { code?: string | null; n?: string | null }) =>
  e.code || e.n || null;
