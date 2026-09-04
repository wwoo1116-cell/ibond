/** 모션 토큰의 TS 짝. **`theme/motion.css` 의 값을 그대로 비춘다** — CSS 커스텀
 * 속성은 `setTimeout` 인자나 인라인 `transition` 문자열이 될 수 없어서, 시간을
 * **값으로** 쓰는 자리에는 숫자가 한 벌 더 있어야 한다.
 *
 * 비춘 값이 어긋나는 것이 이 구조의 유일한 위험이라 `guards/motion-tokens.test.ts`
 * 가 두 파일을 실제로 읽어 대조한다. `theme/ramp.ts` ↔ 다크 헤어라인과 같은 관계다.
 *
 * 규율(v1 §14, 그대로): **모션은 크롬에만.** 차트의 경로 기하는 절대 애니메이션하지
 * 않는다 — 선이 움직이면 그건 장식이 아니라 데이터에 대한 거짓말이 된다.
 */

/** 밀리초. `--sr-motion-*` 와 같은 값이어야 한다. */
export const MOTION = {
  /** 이동 없는 상태 변화 — 호버 틴트, 포커스 링, 칩 */
  fast: 120,
  /** 모든 등장 */
  base: 220,
  /** 모든 퇴장 — 등장보다 항상 짧다 */
  exit: 160,
} as const;

/** `--sr-ease-out` 와 같은 곡선. 이 제품의 **유일한** 곡선이다. */
export const EASE_OUT = 'cubic-bezier(0.32, 0.72, 0, 1)';

/** 이벤트 시점에 OS 설정을 읽는다. 렌더 중이 아니라 핸들러/이펙트에서만 부른다 —
 * 구독하는 스토어가 아니라 그때그때 묻는 값이다. `matchMedia` 가 없는 환경(SSR,
 * jsdom)에서는 "감속 아님" 으로 답한다. */
export function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

/** 감속 설정이면 0, 아니면 준 시간 그대로. JS 가 시간을 값으로 쓰는 **모든** 자리가
 * 이 함수를 지난다 — CSS 블랭킷이 못 닿는 절반이 여기다. */
export function instant(ms: number): number {
  return prefersReducedMotion() ? 0 : ms;
}

/** 프로그램이 스크롤시키는 유일한 경로(커맨드 바 점프)에서 쓴다. 인자로 준
 * `behavior: "smooth"` 는 CSS 의 `scroll-behavior: auto` 를 **이긴다** — 명시가
 * 이기기 때문에, 여기서 한 번 더 물어야 감속 설정이 지켜진다. */
export function scrollIntoViewSafely(el: Element): void {
  el.scrollIntoView({
    behavior: prefersReducedMotion() ? 'auto' : 'smooth',
    block: 'center',
  });
}
