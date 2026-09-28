'use client';

/* 프롭을 **내용**으로 비교한다 — 참조로 비교하면 화면이 번쩍인다 [2026-08-27].
 *
 * ── 무엇이 있었나 (실측 2026-08-27, 라이브) ─────────────────────────────────
 * 커서를 차트 위에 **올려 둔 채** 리드아웃 카드가 생겼다 사라지기를 반복했다.
 * 계측: 마우스를 5px 옮기는 동안 카드가 2번 붙고 2번 떨어졌고, 조회 시점의
 * 카드 개수는 0이었다(커서는 그대로 차트 위).
 *
 * 뿌리는 데이터 이펙트의 의존성이 **전부 참조 타입**이었다는 것이다:
 *
 *     }, [handle, lines, markers, priceLines, markLines, dates, precision]);
 *
 * 호출부가 `dates={view.win.map((p) => p.t)}` 처럼 매 렌더 새 배열을 주면 —
 * 여섯 곳이 그랬다 — 이펙트가 계열을 **전부 지웠다가 다시 만들었다**
 * (`removeLines` → `addLine`). 계열이 사라지는 순간 크로스헤어가 빈 값을 쏘고,
 * `notify(null)` 이 hover 를 지우고, 카드가 언마운트된다. 그리고 그 렌더가
 * 다음 새 배열을 낳으므로 **멈추지 않는 되먹임**이 된다:
 *
 *     hover → setState → 렌더 → 새 배열 → 계열 파괴·재생성 → 크로스헤어 null
 *          → hover 지움 → 렌더 → …
 *
 * ── 왜 호출부가 아니라 여기서 고치는가 [OWNER 2026-08-27 — "부품부로 ㄱㄱ"] ──
 * 여섯 곳을 `useMemo` 로 감싸는 수리도 된다. 그런데 그건 **앞으로 차트를 붙이는
 * 사람이 전부 기억해야 하는 규칙**이고, 이 리포는 그런 규칙이 깨지는 것을 이미
 * 여러 번 봤다(CLAUDE.md 「얼라인」 8 의 그 자리). 부품이 참으면 호출부는
 * 평범하게 쓰면 된다.
 *
 * ── 함수는 비교하지 않는다 ─────────────────────────────────────────────────
 * `color`·`areaColor`·`format` 은 매 렌더 새 화살표인 경우가 많아서(인라인으로
 * 만드는 호출부가 있다) 여기서 비교하면 아무것도 안정되지 않는다. 그래서 이
 * 모듈은 **모양과 값만** 본다:
 *
 *   · 구조 이펙트는 안정된 값으로 돌되, 함수는 **최신 것을 ref 로 읽는다** —
 *     계열을 다시 세우는 순간에는 언제나 그때의 색·서식이 쓰인다.
 *   · 색만 바뀌고 값은 그대로인 경우(MA 색 취향 변경이 그렇다)는 계열을 부수지
 *     않는 **별도의 겉모습 이펙트**가 `applyOptions` 로 입힌다.
 */

import { useRef } from 'react';

/**
 * 내용이 같으면 **이전 참조를 그대로** 돌려준다.
 *
 * 훅 규칙 안에서 안전하다 — 순서가 고정된 `useRef` 하나뿐이고, 렌더 중 ref 를
 * 쓰는 것은 «이전 렌더의 값과 견주는» 이 용도에 한해 React 문서가 인정하는
 * 관용구다(파생 상태 캐시).
 */
export function useStable<T>(next: T, eq: (a: T, b: T) => boolean): T {
  const ref = useRef<T>(next);
  if (ref.current !== next && !eq(ref.current, next)) ref.current = next;
  return ref.current;
}

/** 두 배열을 원소 비교. 길이가 다르면 다르다. */
function sameEach<T>(
  a: readonly T[] | undefined,
  b: readonly T[] | undefined,
  eq: (x: T, y: T) => boolean,
): boolean {
  if (a === b) return true;
  if (a == null || b == null) return a == null && b == null;
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (!eq(a[i]!, b[i]!)) return false;
  return true;
}

/** 값 배열. `null`(그 자리에 값 없음)도 값으로 친다. */
export function sameValues(
  a: readonly (number | null)[] | undefined,
  b: readonly (number | null)[] | undefined,
): boolean {
  return sameEach(a, b, (x, y) => x === y);
}

/** 날짜 축. */
export function sameStrings(
  a: readonly string[] | undefined,
  b: readonly string[] | undefined,
): boolean {
  return sameEach(a, b, (x, y) => x === y);
}

/** 장중 초 축 — 이 앱의 가로축은 수다(`TimeChart.times`). */
export function sameNumbers(
  a: readonly number[] | undefined,
  b: readonly number[] | undefined,
): boolean {
  return sameEach(a, b, (x, y) => x === y);
}

/** `TimeLine`·`ScaleLine` 이 공유하는 «모양» — 함수는 여기 없다. */
type LineShape = {
  id: string;
  values: readonly (number | null)[];
  width?: number;
  dash?: boolean;
  step?: boolean;
  area?: string;
  axis?: string;
  beacon?: boolean;
};

/** 계열의 «틀» — 값은 안 본다. 이것이 같으면 계열을 **다시 안 세운다**. */
export function sameShape(
  a: readonly LineShape[] | undefined,
  b: readonly LineShape[] | undefined,
): boolean {
  return sameEach(
    a,
    b,
    (x, y) =>
      x.id === y.id &&
      x.width === y.width &&
      x.dash === y.dash &&
      x.step === y.step &&
      x.area === y.area &&
      x.axis === y.axis &&
      /* 구슬도 «모양» 이다 — 빼 두면 주선이 바뀌어도 계열을 다시 안 세운다. */
      x.beacon === y.beacon,
  );
}

export function sameLines(
  a: readonly LineShape[] | undefined,
  b: readonly LineShape[] | undefined,
): boolean {
  return sameShape(a, b) && sameEach(a, b, (x, y) => sameValues(x.values, y.values));
}

/** 고·저 표시점. */
export function sameMarkers(
  a: readonly { index: number }[] | undefined,
  b: readonly { index: number }[] | undefined,
): boolean {
  return sameEach(a, b, (x, y) => x.index === y.index);
}

/** 가로 상수선 — 0선·σ 밴드. */
export function samePriceLines(
  a: readonly { value: number; dash?: boolean }[] | undefined,
  b: readonly { value: number; dash?: boolean }[] | undefined,
): boolean {
  return sameEach(a, b, (x, y) => x.value === y.value && x.dash === y.dash);
}

/** 세로 사실선 — «그 날 들어갔다». */
export function sameMarkLines(
  a: readonly { index: number; label?: string; tone?: string }[] | undefined,
  b: readonly { index: number; label?: string; tone?: string }[] | undefined,
): boolean {
  /* `tone` 도 내용이다 — 같은 자리의 선이 색만 바뀌는 일이 실제로 있다(전략
     창에서 거래 하나를 펴면 그 진입선만 잉크가 된다). 빼면 그 변화가 화면에
     안 온다. */
  return sameEach(
    a, b,
    (x, y) => x.index === y.index && x.label === y.label && x.tone === y.tone,
  );
}

/** 우리 가로축의 노드 — 자리·글자·무게. */
export function sameNodes(
  a: readonly { x: number; label: string; weight: number }[] | undefined,
  b: readonly { x: number; label: string; weight: number }[] | undefined,
): boolean {
  return sameEach(a, b, (x, y) => x.x === y.x && x.label === y.label && x.weight === y.weight);
}
