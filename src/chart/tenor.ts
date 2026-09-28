/* 만기 어휘 ↔ 월수 — 커브 차트의 가로축 [2026-08-26 이관].
 *
 * `createYieldCurveChart` 의 가로축은 **월수**다(`baseResolution: 1`). 그래서
 * 이 앱의 만기 이름(`3M`·`1Y`·`10Y`)을 숫자로 바꾸는 자리가 필요하다.
 *
 * ── 왜 `sim/scenario.ts::tenorYears` 를 안 쓰는가 ───────────────────────────
 * 같은 산술이 거기 있다. 그런데 이 리포에는 **`ui`(그리고 그 형제 층)가
 * `@/sim` 에서 값을 임포트하지 않는다**는 규칙이 있다 [2026-08-11] — 화면이
 * 시뮬 엔진을 끌고 들어오면 엔진을 고칠 때 화면이 같이 깨진다. 차트 축은
 * 화면의 일이므로 이 층이 제 것을 진다. 산술이 같으니
 * `guards/chart-tenor.test.ts` 가 **두 벌이 안 갈리는지** 잰다.
 */

/** `3M`→3 · `18M`→18 · `1Y`→12 · `10Y`→120. 못 읽으면 `null`. */
export function tenorMonths(id: string): number | null {
  const m = /^(\d+(?:\.\d+)?)([YMD])$/.exec(id.trim());
  if (!m) return null;
  const n = Number(m[1]);
  if (!Number.isFinite(n)) return null;
  const months = m[2] === 'Y' ? n * 12 : m[2] === 'M' ? n : (n / 365) * 12;
  /* 축은 정수 월을 센다(`baseResolution: 1`). 1일물 같은 것이 0 으로 뭉치면
     커브 왼쪽 끝이 겹치므로 **올림**한다 — 0 개월은 축의 원점이라 데이터가
     설 자리가 아니다. */
  return Math.max(1, Math.round(months));
}

/** 월수를 눈금 글자로. 축에 「120」이 아니라 **「10Y」**가 서게 하는 것. */
export function monthsLabel(months: number): string {
  if (months < 12) return `${months}M`;
  if (months % 12 === 0) return `${months / 12}Y`;
  /* 18개월처럼 안 떨어지는 것은 개월로 읽는 것이 이 데스크의 어휘다. */
  return `${months}M`;
}
