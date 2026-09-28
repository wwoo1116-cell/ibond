'use client';

/* 만기 가로축 — 자리는 **√만기**, 글자와 눈금 선택은 **실제 만기**
 * [OWNER 2026-08-26 — 「√만기 축 — 짧은 쪽에 자리」].
 *
 * ── 왜 라이브러리의 커브 축을 안 쓰는가 ─────────────────────────────────────
 * `createYieldCurveChart` 의 가로축은 **선형 월수**다. 그건 만기 축의 정석이지만
 * 원화 데스크가 실제로 보는 3M~1Y 가 왼쪽 끝에 뭉친다(실측: 10Y 커브에서 3M·6M·9M
 * 세 노드가 1Y 앞 5% 폭 안에 들어간다). 그래서 자리를 √만기로 잡는다 — 순서는
 * 그대로고 짧은 쪽이 펴진다. 채권 데스크의 오래된 관례다.
 *
 * ── 왜 «값만 바꿔 넣기» 로는 안 되는가 ─────────────────────────────────────
 * 라이브러리의 가로축은 **인덱스 간격**이다. 커브 차트는 매 월마다 빈 점
 * (whitespace)을 채워 넣어 «인덱스 간격 = 월 간격» 을 만든다. 그러니 √ 로 스케일한
 * 값을 그냥 먹이면 자리는 바뀌지만 **눈금이 무너진다**: 어느 자리에 글자를 세울지는
 * 점의 «가중치» 가 정하고, 그 가중치를 커브 축은 **값의 배수 관계**로 매기기
 * 때문이다(120·60·36·12·6·3개월). √ 로 스케일한 뒤에는 그 배수 관계가 아무 뜻도
 * 없어서, 10Y 가 가장 낮은 가중치를 받아 좁아지면 제일 먼저 사라지는 일이 생긴다.
 *
 * 그래서 축 자체를 정의한다. 배관은 `horzScale.ts` 가 지고(만기축·숫자축이
 * 공유한다) 이 파일은 **만기 어휘를 자리·글자·무게로 옮기는 일**만 한다.
 * 가로 위치는 √ 로 스케일한 정수가 지고, **가중치와 글자는 그 점의 실제 만기**가
 * 진다. 가중치 사다리는 라이브러리의 커브 축이 쓰는 것을 그대로 가져왔다 —
 * 10년·5년·3년·1년·6개월·3개월 순으로 살아남는다.
 */

import type { ScaleNode } from './horzScale';
import { monthsLabel } from './tenor';

/** √월수를 정수 축으로 펼 때의 배율. 20 이면 3M→35 · 10Y→219 · 30Y→379 라
 *  이웃한 만기끼리 안 뭉치면서 축 해상도가 과하지 않다. */
export const TENOR_SCALE = 20;

/** 월수 → 가로 자리. **이 함수가 이 축의 정의다.** */
export function monthsToX(months: number): number {
  return Math.round(Math.sqrt(months) * TENOR_SCALE);
}

/** 라이브러리 커브 축의 가중치 사다리 — 다만 **실제 월수**로 매긴다. */
export function weightOf(months: number): number {
  if (months % 120 === 0) return 10;
  if (months % 60 === 0) return 9;
  if (months % 36 === 0) return 8;
  if (months % 12 === 0) return 7;
  if (months % 6 === 0) return 6;
  if (months % 3 === 0) return 5;
  return 4;
}

/** 만기 목록(월수) → 축 노드들. 같은 자리로 떨어지는 만기는 앞엣것만 남는다. */
export function tenorNodes(monthsList: readonly number[]): ScaleNode[] {
  const seen = new Set<number>();
  const out: ScaleNode[] = [];
  for (const m of monthsList) {
    const x = monthsToX(m);
    if (seen.has(x)) continue;
    seen.add(x);
    out.push({ x, label: monthsLabel(m), weight: weightOf(m) });
  }
  return out;
}
