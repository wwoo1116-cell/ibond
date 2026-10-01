/**
 * 숫자를 글자로 바꾸는 일은 **이 파일 하나**가 한다. [2026-09-28 디자인 문법 레인]
 *
 * ── 왜 모았나 ──────────────────────────────────────────────────────────────
 * 같은 이름의 도우미가 여섯 파일에 각각 선언돼 있었고, **이미 갈려 있었다**:
 *   · `sbp` 가 `Bonds` 에서만 `bp` 를 문자열에 구워, 교체 패널이 `+1.5bpbp` 를 냈다
 *   · 같은 잔존이 `8M`(Credit·Curve)과 `243일`(Feed)로 갈렸다 — 09-23 오너 규칙은 «일» 이다
 *   · 같은 빈값이 `—`·`·`·`''` 셋으로 갈렸다
 *   · `hms` 가 세 벌 중 한 벌만 24시를 접었다
 * 갈렸다는 것보다 나쁜 것은 **아무도 모른 채** 갈려 있었다는 사실이다. 한 화면에서
 * 같은 양이 두 어휘로 말해지면 읽는 사람이 둘을 다른 것으로 읽는다.
 * (v2 캐논 규칙 8 「같은 것은 한 번만 만든다」 · `guards/format-single-source.test.ts`)
 *
 * ── 정밀도는 «동결» 이다 ────────────────────────────────────────────────────
 * 이 레인은 디자인 작업이고 **보이는 수는 하나도 안 바뀐다**(지문 대조 0건이 게이트).
 * 그래서 아래 자릿수는 고르는 것이 아니라 «지금 화면이 내는 그대로» 를 옮겨 적은 것이다.
 * 바꾸려면 오너 판정이 먼저다.
 *
 *   금리        세 자리. 단 피드는 0.25bp 자리만 네 자리(`fmtQuoteYield`) — 09-23
 *   변화        bp 한 자리. 부호는 U+2212(하이픈 아님) 또는 화살표(`ui/Delta`)
 *   수량        억, 0.1 단위. 「그래야 합산이 가능」 [OWNER 2026-09-03]
 *   시각        HH:MM:SS, 24시를 접는다(장중 초가 86,400 을 넘는 날이 있다)
 *   잔존        만기 / N일(1년 안) / N.N년 — 09-23. 「0.2년이라 쓰면 만기가 코앞인 게 안 보인다」
 *   빈값        em dash. 「빈칸은 로딩으로 읽힌다」 [v2]. 예외 둘은 아래에 적었다
 */

/** 진짜 마이너스(U+2212). 하이픈은 폭이 달라 tabular 정렬을 깨뜨린다. */
export const MINUS = '−';

/**
 * 빈값 표식. **0.00 도 빈칸도 아니다** [v2 `lib/format.ts`].
 *
 * ⚠예외 둘 — 둘 다 «모른다» 가 아니라 다른 뜻이라 빈칸이 맞다:
 *   · 피드의 값 없는 칸 = «아직 못 읽었다»(원문은 흘리고 칸만 비운다) [OWNER 2026-09-22]
 *   · 단가 빈칸 = «못 잰다»(제원이 없거나 만기가 지났다) [2026-09-23]
 */
export const EMDASH = '—';

const p2 = (n: number) => String(n).padStart(2, '0');

/* ─────────────────────────────────────────────────────────── 금리·변화 */

/** 금리 레벨, 세 자리. 4.197 */
export function fmtYield(v?: number | null): string {
  return v == null ? EMDASH : v.toFixed(3);
}

/**
 * 호가 금리 — ★0.25bp 자리만 **네 자리**로 적는다 [2026-09-23].
 *
 * 세트호가(두 다리의 중간값)가 서는 자리라 셋째 자리로 뭉개면 «세트라는 사실» 이
 * 화면에서 사라진다: 3.9975 → 3.998 은 그냥 다른 호가로 읽힌다. 0.5bp 격자 값은
 * 지금처럼 세 자리다(3.405).
 *
 * 빈값이 `''` 인 것은 이 함수가 **피드 전용**이기 때문이다(위 EMDASH 예외 참조).
 */
export function fmtQuoteYield(v?: number | null): string {
  if (v == null) return '';
  return Math.round(v * 10000) % 10 === 0 ? v.toFixed(3) : v.toFixed(4);
}

/**
 * 부호 있는 수. `+4.3` / `−12.5` (v2 `fmtBp` 와 같은 셈).
 *
 * `digits` 를 안 주면 반올림하지 않는다 — 원 단위처럼 이미 정해진 자릿수로
 * 들어오는 값을 여기서 다시 깎지 않기 위해서다.
 */
export function fmtSigned(v?: number | null, digits?: number): string {
  if (v == null) return EMDASH;
  const s = digits == null ? String(Math.abs(v)) : Math.abs(v).toFixed(digits);
  return v < 0 ? `${MINUS}${s}` : `+${s}`;
}

/** 부호 있는 bp, 한 자리. `+4.3` / `−12.5` */
export function fmtBp(v?: number | null, digits = 1): string {
  return fmtSigned(v, digits);
}

/** 부호 있는 bp에 단위까지. `+4.3bp`
 *
 * ★단위를 함수가 진다 — 부르는 쪽이 `${fmtBp(v)}bp` 로 붙이던 자리가 하나 있었고,
 *   그 함수가 이미 bp 를 굽고 있어서 `+1.5bpbp` 가 나왔다(`Bonds.tsx:486`, 09-23).
 */
export function fmtBpUnit(v?: number | null, digits = 1): string {
  return v == null ? EMDASH : `${fmtBp(v, digits)}bp`;
}

/** 부호 **없는** bp — 스프레드·반스프레드처럼 크기만 있는 양. `0.5` */
export function fmtBpLevel(v?: number | null, digits = 1): string {
  return v == null ? EMDASH : v.toFixed(digits);
}

/** 축 눈금은 한 단 거칠게 — % 두 자리 [v2 `fmtAxis`].
 *  눈금이 그림보다 눈에 띄면 읽는 사람이 선이 아니라 눈금을 읽는다. */
export function fmtAxis(v: number): string {
  return v.toFixed(2);
}

/** 단가(원), 두 자리. 빈값은 `''` — 「못 잰다」이지 「0원」이 아니다. */
export function fmtPx(v?: number | null): string {
  return v == null ? '' : v.toFixed(2);
}

/* ─────────────────────────────────────────────────────────── 수량·비율 */

/** 수량 → 억. 기본단위 100억 [OWNER 2026-09-03 「그래야 합산이 가능」]. */
export function fmtLot(a?: number | null): string {
  return a == null || !a ? EMDASH : `${Math.round(a * 10) / 10}억`;
}

/** 같은 수량인데 빈값이 `''` — 산문 안(피드·동향)에서 쓴다. */
export function fmtLotBlank(a?: number | null): string {
  return a == null || !a ? '' : `${Math.round(a * 10) / 10}억`;
}

/** 비율. 기본 두 자리. */
/**
 * 돈 한 칸 — **100억 살 때의 값**. 들어오는 것은 서버가 준 «단가 원»(액면 1만원)이고
 * 100억 기준은 ×1e6 이다.
 *
 * ★왜 이 함수가 여기 있나 [2026-10-01]: 알람 배너가 이 서식을 **손으로 짰다가**
 *   `format-single-source` 가드에 걸렸다(`toFixed`·`toLocaleString` 셋). 서식은 이
 *   파일 하나가 진다 — 같은 양이 자리마다 다른 어휘로 적히면 한쪽만 낡는다.
 * ★왜 bp 옆에 돈을 적나: bp 는 **짧은 잔존에서 돈이 아니다**. 잔존 0.01년의 3bp 는
 *   100억에 3만원이고 1년이면 289만원이다(실측 1,000배). 환산은 서버가 한다.
 */
export function fmtWon10b(wonPer10k?: number | null): string {
  if (wonPer10k == null) return EMDASH;
  const v = wonPer10k * 1e6;
  const a = Math.abs(v);
  if (a >= 1e8) return `${fmtRatio(v / 1e8, 1)}억`;
  if (a >= 1e4) return `${fmtCount(Math.round(v / 1e4))}만`;
  return `${fmtCount(Math.round(v))}원`;
}


export function fmtRatio(v?: number | null, digits = 2): string {
  return v == null ? EMDASH : v.toFixed(digits);
}

/** 퍼센트, 부호 없음. `62%` */
export function fmtPct(v?: number | null, digits = 0): string {
  return v == null ? EMDASH : `${v.toFixed(digits)}%`;
}

/** 천단위 콤마. ★지금 콤마를 찍는 자리에만 쓴다 — 안 찍던 칸에 넣으면 값이 바뀐 것으로 잡힌다. */
export function fmtCount(n: number): string {
  return n.toLocaleString('ko-KR');
}

/* ─────────────────────────────────────────────────────────── 시각·기간 */

/** 장중 초 → `HH:MM:SS`. ★24시를 접는다 — 세 벌 중 한 벌만 접고 있었다. */
export function fmtHms(t?: number | null): string {
  if (t == null) return '';
  return `${p2(Math.floor(t / 3600) % 24)}:${p2(Math.floor((t % 3600) / 60))}:${p2(Math.floor(t % 60))}`;
}

/** 장중 초 → `HH:MM`. */
export function fmtHm(t?: number | null): string {
  if (t == null) return '';
  return `${p2(Math.floor(t / 3600) % 24)}:${p2(Math.floor((t % 3600) / 60))}`;
}

/* ── 시세 테이프의 시각 [2026-10-01] ──────────────────────────────────────────
 * 여러 날을 한 축에 잇는 차트는 «장중 초» 로는 날이 안 선다. 테이프의 자리는
 * **에포크 초**이되 KST 벽시계를 UTC 로 흘린 것이다(`lib/pxTape.ts::epochOf`) —
 * 그래서 읽을 때도 UTC 손잡이로 읽어야 벽시계가 그대로 나온다. 세 벌 다 ISO 다. */

/** 테이프 자리 → `MM-DD`. 날이 바뀌는 눈금. */
export function fmtTapeDay(t: number): string {
  const d = new Date(t * 1000);
  return `${p2(d.getUTCMonth() + 1)}-${p2(d.getUTCDate())}`;
}

/** 테이프 자리 → `HH:MM`. 하루 안의 눈금. */
export function fmtTapeHm(t: number): string {
  const d = new Date(t * 1000);
  return `${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())}`;
}

/** 테이프 자리 → `YYYY-MM-DD HH:MM`. 크로스헤어와 리드아웃의 시각. */
export function fmtTapeAt(t: number): string {
  const d = new Date(t * 1000);
  return `${d.getUTCFullYear()}-${p2(d.getUTCMonth() + 1)}-${p2(d.getUTCDate())} ${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())}`;
}

/**
 * 잔존 — ★1년 안쪽은 «일» 로 적는다 [2026-09-23].
 *
 * 「0.2년」이라 적으면 만기가 코앞인 것이 안 보인다. 그 구간은 하루가 곧 값이다 —
 * 잔존 78일이면 1원이 4.7bp 이고, 같은 1원이 30년물에선 0.06bp 다.
 */
export function fmtTtm(t?: number | null): string {
  if (t == null) return '';
  if (t < 0) return '만기';
  return t < 1 ? `${Math.round(t * 365)}일` : `${t.toFixed(1)}년`;
}

/** 축 눈금용 잔존 — 「2.0년」이 아니라 「2년」. 눈금에 뜻 없는 소수는 잡음이다. */
export function fmtTtmTick(t: number): string {
  if (t === 0) return '0';
  if (t < 1) return `${Math.round(t * 365)}일`;
  return `${Number.isInteger(t) ? t : t.toFixed(1)}년`;
}

/** 잔존 구간. `10.5~30.0년` */
export function fmtTtmRange(lo: number, hi: number): string {
  return `${lo}~${hi}년`;
}

/** 나이 → 초·분·시간. 호가가 선 지 얼마나 됐나. */
export function fmtAge(sec: number): string {
  return sec < 60 ? `${Math.round(sec)}초` : sec < 3600 ? `${Math.round(sec / 60)}분` : `${(sec / 3600).toFixed(1)}시간`;
}

/** 분 단위. `10분` */
export function fmtMin(sec: number): string {
  return `${Math.round(sec / 60)}분`;
}

/** 만기일 `YYYY-MM-DD` → `YY-MM-DD`. 칸 폭을 두 글자 돌려받는다. */
export function fmtMatShort(iso?: string | null): string {
  return iso ? iso.slice(2) : '';
}
