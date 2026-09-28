/**
 * 표의 열 폭 — **서식 최대치**에서 나온다. [2026-09-28, v2 `table/columns.ts` 규율]
 *
 * ── 규칙 한 줄 ─────────────────────────────────────────────────────────────
 * 열 폭은 그 열의 **서식**이 낼 수 있는 가장 넓은 글자에서 나온다. 오늘 자료에서
 * 나오는 것이 아니다. `tabular-nums` 라 숫자는 모두 같은 폭이므로, 가장 넓은
 * 렌더링은 **고정된 본보기 문자열**이고 그래서 격자가 안 움직인다 — 탭을 바꿔도,
 * 정렬을 바꿔도, 값이 커져도.
 *
 * ── 왜 필요했나 ────────────────────────────────────────────────────────────
 * 이 앱의 표는 셋이 제각각이었다: 피드만 서식 최대치(`--kb-cols`)를 쓰고, `.kb-tbl`
 * 다섯은 `table-layout: fixed` 인데 **폭을 하나도 안 줘서** 열이 똑같이 나뉘었고
 * (그래서 종목명은 잘리고 「나이」는 텅 비었다), 동향의 커브 표만 인라인 px 였다.
 *
 * ── 폭을 어떻게 재나 ───────────────────────────────────────────────────────
 * `CH_PX` 는 **화면에서 잰 값**이다(`probe_screen.mjs` 가 숫자 칸에 글자를 넣어
 * 잰다) — 「재는 대상이 곧 그리는 대상이어야 한다」(v2 ch 판례: 한 표에서 ch 가
 * 셋이었고 그래서 열이 26% 넓게 그려졌다). 한글은 `ch` 에 비례하지 않아 따로 센다.
 */

/** 숫자 한 글자(`0`)의 실제 advance. 12px Pretendard SR 의 숫자 칸에서 실측. */
export const CH_PX = 7.15;

/** 한글 한 글자 — 폭이 «글자 크기» 에 붙는다(v2 §5.2). 12px 칸 기준. */
export const HANGUL_PX = 12;

/** 셀 좌우 안쪽 여백(`.kb-tbl td`). */
export const CELL_PAD = 10;

/** 카드 안쪽 선과 맞추는 첫·끝 열의 바깥 여백 — 카드 머리의 `paddingX` 와 같다. */
export const CELL_INSET = 16;

/** 본보기 문자열의 렌더 폭(px). 한글과 숫자를 따로 센다. */
export function px(sample: string, pad = CELL_PAD * 2): number {
  let w = 0;
  for (const ch of sample) w += /[ㄱ-힝]/.test(ch) ? HANGUL_PX : CH_PX;
  return Math.ceil(w + pad);
}

/**
 * 열마다 «문법이 낼 수 있는 가장 넓은 글자».
 *
 * 화살표가 들어간 것은 D4.1 때문이다 — 변화 칸은 `↘ 999.9` 로 적힌다.
 */
export const WIDEST = {
  yield: '0.000',
  deltaBp: '↘ 999.9',
  age: '12.3시간',
  count4: '9,999',
  count3: '999',
  lot: '1000억',
  ttm: '365일',
  tenor: '50년',
  minutes: '999분',
  kind: '회사채 AA−',
  ttmRange: '10.5~30.0년',
  /** ★「기준」은 «종목명 + bp» 라 사실상 **이름 칸**이다 — 실측 최대 134px
   *  (「메리츠캐피탈251-2 −4.8bp」). 서식으로는 못 잡으니 실측으로 잡는다. */
  basis: '메리츠캐피탈251-2 ↘ 4.8bp',
  bar: '매도/매수',
} as const;

/** `null` 은 «남는 폭을 먹는» 열(이름 열 하나뿐이어야 한다). */
export type ColSpec = readonly (number | null)[];

const w = px;
const edge = (s: string) => px(s, CELL_PAD + CELL_INSET);

/**
 * 표마다의 열 폭. 차례는 **DOM 의 `<th>` 차례**와 같아야 한다.
 *
 * ★이름 열만 `null` 이다. 둘 이상을 `null` 로 두면 남는 폭이 갈려 두 열 다
 *   자기 최대치를 못 받는다 — 그럴 바에는 어느 쪽이 늘어날지 정하는 것이 낫다.
 */
export const TABLES: Record<string, ColSpec> = {
  /** 종목 화면 오른쪽 딜러 표 — `Bonds.tsx` */
  dealers: [null, w(WIDEST.yield), w(WIDEST.yield), w(WIDEST.age), edge(WIDEST.count3)],
  /** 크레딧 매수 니즈 — `Credit.tsx` */
  needs: [null, w(WIDEST.kind), w(WIDEST.ttmRange), w(WIDEST.lot), edge(WIDEST.basis)],
  /** 크레딧 오퍼 — `Credit.tsx`. YTM 칸은 «환산·추정» 배지를 품는다. */
  offers: [null, w(WIDEST.ttm), w(WIDEST.deltaBp), w(WIDEST.yield) + 30, edge(WIDEST.lot)],
  /** 동향 딜러 리더보드 — `Trends.tsx` */
  leaderboard: [
    null,
    w(WIDEST.count4),
    w(WIDEST.bar),
    w(WIDEST.count3),
    w(WIDEST.count3),
    edge(WIDEST.minutes),
  ],
  /** 동향 커브 오늘 — `Trends.tsx`. 첫 열(연물)이 바깥 여백을 진다. */
  curveToday: [
    edge(WIDEST.tenor),
    null,
    w(WIDEST.yield),
    w(WIDEST.yield),
    w(WIDEST.deltaBp),
    edge(WIDEST.count3 + ' ▲'),
  ],
};
