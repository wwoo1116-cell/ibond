/* 부호 틴트 — 히트맵 셀의 배경. v1 `theme/sign-tint.ts` 의 이식(값·규칙 그대로).
 *
 * 규칙 [v1 OWNER, 2026-08-06]: **색은 부호만 말한다.** 크기는 농도가 말한다.
 * 그래서 양수는 `--sr-up` 계열, 음수는 `--sr-down` 계열이고 둘 사이에 제3의 색조는
 * 없다. 회색조로 인쇄해도 농도 순서가 그대로 남는다.
 *
 * ── 한 셀에서 색은 한 채널만 쓴다 ──────────────────────────────────────────
 * 틴트가 칠해진 셀의 **글자는 잉크다.** 배경이 이미 부호를 말하므로 숫자까지 같은
 * 색조로 칠하면 사실이 중복될 뿐 아니라 글자가 배경에 먹힌다. v1 의 첫 구현이
 * 정확히 그랬고, 라이트에서 −530.9억이 파랑 위 파랑이 되어 안 읽혔다.
 *
 * 농도를 낮추면 되는 줄 알았는데 재보니 **어떤 농도에서도 안 됐다**: 같은 부호 틴트
 * 위의 방향색 텍스트가 30% 에서 3.0:1, 42% 에서 2.5:1, 62% 에서 1.8:1 이다. 4.5 를
 * 넘는 지점이 없다. 농도 조절 문제가 아니라 범주적 규칙이다.
 *
 * `.sr-up`/`.sr-down` 클래스는 **틴트가 없는 곳** 전용이다.
 *
 * ── 왜 문자열을 돌려주나 ───────────────────────────────────────────────────
 * 혼합 비율이 셀마다 다르므로 미리 만들어 둘 수 있는 클래스가 아니다. 런타임
 * 인라인 스타일이 유일한 방법이고, 브라우저가 토큰을 해석하므로 테마가 뒤집혀도
 * 자동으로 따라온다(캔버스와 달리 DOM 은 `var()` 를 이해한다). 색 리터럴이 없어서
 * `guards/color-source.test.ts` 의 "hex 는 direction.css 에만" 규칙도 지킨다.
 */

/** 0 이 아닌 값이 배경과 구별되지 않는 것을 막는 하한. 이 아래로는 "칠했지만
 * 안 보이는" 상태가 되어 빈 칸과 작은 값이 같아 보인다. 그건 거짓말이다. */
export const MIN_MIX = 8;

/** 상한. 구속 조건은 **다크에서 잉크 대비**다 — v1 실측: 다크 62% 에서 5.06:1,
 * 75% 에서 3.99:1 로 깨진다. 라이트는 75% 에서도 4.89 로 여유가 있다. 55% 면
 * 다크에서 5.7:1 언저리라 토큰을 나중에 손봐도 하한이 남는다. */
export const MAX_MIX = 55;

/**
 * @param value 셀의 값. 0 이면 틴트 없음(빈 배경).
 * @param scale 이 표에서 |값|의 기준 최댓값. 0 이하이면 비교 대상이 없다는 뜻이라
 *              칠하지 않는다.
 */
export function tintFor(value: number, scale: number): string | undefined {
  if (!Number.isFinite(value) || value === 0) return undefined;
  if (!Number.isFinite(scale) || scale <= 0) return undefined;

  // 제곱근 스케일: 선형으로 잡으면 큰 값 하나가 나머지를 전부 옅은 회색으로
  // 눌러버려 표가 "한 칸만 있는" 것처럼 보인다.
  const frac = Math.min(1, Math.sqrt(Math.abs(value) / scale));
  const mix = Math.round(MIN_MIX + frac * (MAX_MIX - MIN_MIX));
  const hue = value > 0 ? '--sr-up' : '--sr-down';
  // 섞는 상대가 `--sr-card` 인 이유: 이 표는 창(카드) 위에 서고, 틴트 0% 는 그
  // 면과 같은 색이어야 한다. 페이지 바탕과 섞으면 옅은 값이 카드 위에서 얼룩진다.
  return `color-mix(in srgb, var(${hue}) ${mix}%, var(--sr-card))`;
}

/** 방향색 자체(글자용). **틴트가 안 칠해진 표면에서만** 쓴다 — 위 주석 참조.
 *
 * 0 은 방향이 아니므로 잉크로 남는다. 0 을 빨강이나 파랑으로 칠하면 있지도 않은
 * 부호를 주장하게 된다. */
export function directionVar(value: number): string {
  if (!Number.isFinite(value) || value === 0) return 'var(--color-fg)';
  return value > 0 ? 'var(--sr-up)' : 'var(--sr-down)';
}
