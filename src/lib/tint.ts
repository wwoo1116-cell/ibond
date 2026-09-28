/**
 * 변화 셀의 네 부품 — 틴트 · 방향 클래스 · 화살표 · 부호 없는 숫자.
 *
 * `sauron-v2/src/table/tint.ts` 에서 «변화 열» 몫만 옮겨 왔다(매트릭스·모멘텀
 * 눈금 둘은 이 앱에 대응하는 화면이 없어 안 가져왔다). 규약은 한 글자도 안 바꿨다 —
 * 두 앱이 같은 양을 같은 어휘로 말해야 한다는 것이 이 이식의 목적이다.
 *
 * v1 §4 의 두 규칙이 이 램프가 존재하는 이유다:
 *   · 부호 있는 수만 색을 가진다. **레벨은 잉크다.**
 *   · 바닥 아래에는 틴트가 **아예 없다.** 0.2bp 는 «옅은 움직임» 이 아니라 잡음이고,
 *     그걸 칠하면 눈이 잡음을 신호로 읽도록 훈련된다.
 */
import type React from 'react';

/** 이 아래로는 틴트가 없다(bp). */
export const TINT_FLOOR = 0.5;

/** 틴트가 가장 진해지는 지점(bp). */
export const TINT_CEIL = 10;

/** 변화의 알파. 바닥 아래는 0, 그 위로는 |v| 에 단조. */
export function tintAlpha(v: number | null | undefined): number {
  if (v == null) return 0;
  const a = Math.abs(v);
  if (a < TINT_FLOOR) return 0;
  const t = Math.min(1, (a - TINT_FLOOR) / (TINT_CEIL - TINT_FLOOR));
  return Number((0.06 + t * 0.14).toFixed(3));
}

/** 숫자 자체를 칠하는 클래스. **레벨은 절대 이걸 안 부른다.** */
export function directionClass(v: number | null | undefined): string {
  if (v == null || v === 0) return 'sr-flat';
  return v > 0 ? 'sr-up' : 'sr-down';
}

/** 변화 셀의 바탕. 글자와 **같은 두 변수**를 쓰므로 틴트가 제 숫자와 방향을 두고
 *  다툴 수가 없다. */
export function tintStyle(v: number | null | undefined): React.CSSProperties | undefined {
  const alpha = tintAlpha(v);
  if (alpha === 0) return undefined;
  const hue = v! > 0 ? 'var(--sr-up)' : 'var(--sr-down)';
  return { backgroundColor: `color-mix(in srgb, ${hue} ${Math.round(alpha * 100)}%, transparent)` };
}

/**
 * D4.1 — 부호를 «색» 이 아니라 **모양**으로도 말한다 [OWNER 2026-09-28 채택].
 *
 * 맨 `+`/`−` 도 색 단독 금지(WCAG 1.4.1)는 만족하지만 얇다 — 마이너스는 획 하나라
 * 작은 글자에서, 특히 틴트 위에서 잃기 쉽다. 화살표는 방향이 **모양에** 들어 있어
 * 색이 유일한 채널이 아니라 보강이 된다.
 *
 * 0 에는 화살표가 없다 — 0 은 방향이 없고, 그리면 있다고 주장하는 것이 된다.
 */
export function directionGlyph(v: number | null | undefined): string {
  if (v == null || v === 0) return '';
  return v > 0 ? '↗' : '↘';
}

/** 부호를 뗀 숫자 — 이제 화살표가 그것을 진다. 폭이 다른 `+`/`−` 가 앞에 붙으면
 *  `tabular-nums` 를 켠 이유가 사라진다. */
export function unsignedDelta(text: string): string {
  return text.replace(/^[+−-]/, '');
}
