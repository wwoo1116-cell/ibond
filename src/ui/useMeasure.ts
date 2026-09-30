"use client";

/* Measure an element's content box so the hand-rolled charts fit the pane on
 * any viewport. A callback ref measures synchronously on mount (more reliable
 * than useRef + useEffect here) and a ResizeObserver keeps it current.
 * Returns [ref, width, height].
 *
 * ★진짜 «내용 상자» 를 잰다 [2026-09-29]. 종전에는 `clientWidth/Height` 였는데
 *   그건 **패딩 상자**다 — 주석은 content box 라고 적고 있었고, 재는 자리에 패딩이
 *   없는 동안은 둘이 같아서 아무도 안 알아챘다. 「한 화면」 레인에서 재는 자리를
 *   `.sr-plot`(패딩 `0 4px 4px`)으로 옮기자 즉시 드러났다: 그림이 세로 4px ·
 *   가로 8px 커져서 제 상자를 넘었고(실측 243 상자에 247), `overflow: hidden` 이
 *   그것을 **조용히** 잘랐다. 패딩을 뺀 수를 주는 것이 답이다 — 패딩은 그림이
 *   숨 쉬는 자리이고, 그림에게 «네 칸» 이라고 말해 줄 수는 없다. */

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
          /* clientWidth/Height 는 패딩을 포함한다 — 빼야 내용 상자다. */
          const cs = getComputedStyle(node);
          const px = (v: string) => parseFloat(v) || 0;
          const w = Math.max(0, node.clientWidth - px(cs.paddingLeft) - px(cs.paddingRight));
          const h = Math.max(0, node.clientHeight - px(cs.paddingTop) - px(cs.paddingBottom));
          return prev.w === w && prev.h === h ? prev : { w, h };
        });
      read();
      ro.current = new ResizeObserver(read);
      ro.current.observe(node);
    }
  }, []);
  return [refCb, size.w, size.h];
}
