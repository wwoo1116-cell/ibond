"use client";

/* Measure an element's content box so the hand-rolled charts fit the pane on
 * any viewport. A callback ref measures synchronously on mount (more reliable
 * than useRef + useEffect here) and a ResizeObserver keeps it current.
 * Returns [ref, width, height]. */

import { useCallback, useRef, useState } from "react";

export function useMeasure<T extends HTMLElement>(): [
  (node: T | null) => void,
  number,
  number,
] {
  const [size, setSize] = useState({ w: 0, h: 0 });
  const ro = useRef<ResizeObserver | null>(null);
  const refCb = useCallback((node: T | null) => {
    ro.current?.disconnect();
    if (node) {
      /* 값이 같으면 이전 객체를 돌려준다 — 새 객체는 값이 같아도 리렌더다.
       * RO 발화마다 무조건 리렌더하던 것이 스크롤바 플립과 만나면 진동의
       * 연료가 된다 (2026-08-18 실측: svg 1864 vs host 1849 의 16px 상시
       * 가로 스크롤바). */
      const read = () =>
        setSize((prev) => {
          const w = node.clientWidth;
          const h = node.clientHeight;
          return prev.w === w && prev.h === h ? prev : { w, h };
        });
      read();
      ro.current = new ResizeObserver(read);
      ro.current.observe(node);
    }
  }, []);
  return [refCb, size.w, size.h];
}
