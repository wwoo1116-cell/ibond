'use client';

/* 캔버스에 넘길 색 — **산 DOM 에서 읽는다** [2026-08-26 라이트웨이트 이관].
 *
 * ── 왜 이 파일이 있는가 ──────────────────────────────────────────────────────
 * CDS `CartesianChart` 는 SVG 라 `stroke="var(--sr-up)"` 한 줄이면 끝이었다.
 * `lightweight-charts` 는 **캔버스**다 — `strokeStyle` 에 넣을 **문자열**을
 * 달라고 하고, 캔버스는 `var(...)` 를 못 푼다. 그래서 토큰과 캔버스 사이에
 * 다리가 필요하다.
 *
 * ── 실측 판례: 이 다리를 잘못 놓으면 조용히 얼어붙는다 ──────────────────────
 * 하니스 `src/chart/CandidateB.tsx` 가 마운트할 때 색을 한 번 읽어 옵션에
 * 박아 뒀다. 그래서 **다크로 토글해도 차트만 라이트 색으로 남았다**. 에러는
 * 없다 — 캔버스는 시킨 색을 그릴 뿐이다. 이 리포가 `guards/color-source.test.ts`
 * 로 «hex 는 direction.css 에만» 을 지켜 온 이유가 그 종류의 침묵이고,
 * 캔버스는 그 가드의 사각지대다(그릴 때 색이 문자열이라 grep 으로는 멀쩡하다).
 *
 * 그래서 규칙 둘:
 *   ① **읽는 시점**은 마운트가 아니라 **스킴이 바뀔 때마다**다(`useLwPalette`).
 *   ② **읽는 대상**은 `document.documentElement` 가 아니라 **차트가 실제로 선
 *      그 엘리먼트**다. CDS `ThemeProvider` 는 팔레트를 루트가 아니라 자기
 *      래퍼의 **인라인 스타일**로 뿌리므로(그 사실은 providers.tsx 주석에도
 *      적혀 있다), 루트에서 읽으면 빈 문자열이 나온다. 컨테이너에서 읽으면
 *      상속으로 전부 보인다 — `--color-*`(CDS)도 `--sr-*`(direction.css)도.
 *
 * ── 변환하지 않는다 ─────────────────────────────────────────────────────────
 * `getPropertyValue` 는 `rgb(9, 133, 81)` 이나 `#0a0b0d` 를 준다. 캔버스의
 * `strokeStyle`·`fillStyle`·`createLinearGradient` 는 그 둘을 그대로 받는다.
 * 그래서 hex 파싱을 **안 한다** — 파싱하는 순간 이 파일이 색을 «만드는» 것이
 * 되고, 그건 규칙 3(hex 는 direction.css 에만)을 캔버스로 우회하는 것이다.
 */

import { useEffect, useState } from 'react';

import type { CustomColorParser, Rgba } from 'lightweight-charts';

import { useScheme } from '@/app/providers';

/** 이 앱이 캔버스에 넘기는 색 전부. 늘리려면 여기 한 줄을 더한다 —
 *  그 한 줄이 «그 변수 이름이 정말 있는지 확인했다» 는 뜻이다
 *  (`guards/css-token-names.test.ts` 와 같은 규율). */
export type LwPalette = {
  /** 글자·눈금 */
  fg: string;
  fgMuted: string;
  /** 바탕(투명으로 두면 캔버스가 검게 나온다 — 아래 `background` 참조) */
  bg: string;
  /** 격자·테두리 */
  line: string;
  lineHeavy: string;
  /** 방향 쌍 — 주선이 쓴다 */
  up: string;
  down: string;
  /** 기준선 넷 */
  refCd: string;
  refPolicy: string;
  refFut: string;
  refRoll: string;
  /** 축 글자체. 캔버스는 `font-family` 도 상속을 못 받는다 — 안 주면
   *  라이브러리 기본(Trebuchet MS)이 나와 화면에서 그 축만 다른 글자가 된다. */
  fontFamily: string;
  /** `fgMuted` 를 반쯤 지운 것. 커브의 **전일 선**이 쓴다 — CDS 판이
   *  `color=fgMuted` 에 `strokeOpacity={0.5}` 를 겹쳐 쓰던 그 색이다.
   *  캔버스에는 불투명도 손잡이가 따로 없어 색 자체가 반투명이어야 한다. */
  fgMutedSoft: string;
  /**
   * 임의의 CSS 색 표현을 **그 자리에서 계산해** 준다 — `var(--sr-up)` 처럼.
   *
   * 팔레트는 이 앱이 «자주 쓰는» 색을 미리 읽어 두지만, 화면마다 제 색이 있다
   * (시뮬 케이스 넷·모형 계열 등). 캔버스는 `var()` 를 못 푸므로 그 색들도
   * 누군가 풀어 줘야 하고, 그 자리가 여기다. 호출부가 CSS 변수 이름을 그대로
   * 들고 있어도 되고(그게 이 리포의 어휘다), 색 리터럴은 여전히 안 생긴다.
   */
  resolve: (css: string) => string;
  /**
   * 색을 흐리게 — `dim('var(--sr-up)', 35)`.
   *
   * 캔버스에는 불투명도 손잡이가 따로 없다(CDS 의 `strokeOpacity` 자리). 색
   * 자체가 반투명이어야 하고, **섞는 계산은 브라우저가 한다**(`color-mix`).
   */
  dim: (css: string, percent: number) => string;
};

/** 읽을 변수 이름 ↔ 결과 키. 이름을 틀리면 빈 문자열이 나오고 캔버스는
 *  **검게** 그린다 — CSS 라면 선언이 무효가 되어 안 그려질 뿐이지만
 *  캔버스에서는 틀린 색이 **그려진다**. 그래서 아래 `readPalette` 가
 *  빈 값을 잡아 `fallback` 으로 떨어뜨린다. */
/** 변수 하나로 곧장 떨어지는 것들. 나머지 셋은 `readPalette` 가 조립한다. */
type ColorKey = Exclude<keyof LwPalette, 'fontFamily' | 'fgMutedSoft' | 'resolve' | 'dim'>;

const VARS: Record<ColorKey, string> = {
  fg: '--color-fg',
  fgMuted: '--color-fgMuted',
  bg: '--color-bg',
  line: '--color-bgLine',
  lineHeavy: '--color-bgLineHeavy',
  up: '--sr-up',
  down: '--sr-down',
  refCd: '--sr-ref-cd',
  refPolicy: '--sr-ref-policy',
  refFut: '--sr-ref-fut',
  refRoll: '--sr-ref-roll',
};

/**
 * 색을 반투명하게 — **계산은 브라우저가 한다.**
 *
 * 직접 섞으려면 `rgb(...)`/`#hex` 를 파싱해 알파를 붙여야 하고, 그 순간 이
 * 파일이 색을 «만드는» 것이 되어 «색 리터럴은 direction.css 한 곳» 규칙을
 * 캔버스로 우회하게 된다. 대신 문서 안에 잠깐 프로브를 세워 `color-mix` 를
 * 시키고 계산값(`rgba(...)`)을 받아 온다. 우리 코드에는 색 산술이 없다.
 */
function computeColor(host: Element, expr: string): string {
  const probe = document.createElement('span');
  probe.style.color = expr;
  probe.style.display = 'none';
  host.appendChild(probe);
  const out = getComputedStyle(probe).color;
  host.removeChild(probe);
  return out;
}

function soften(host: Element, color: string, percent: number): string {
  return computeColor(host, `color-mix(in srgb, ${color} ${percent}%, transparent)`) || color;
}

/* 색 문자열을 **라이브러리가 읽을 수 있는 꼴로** 되돌리는 캔버스.
   한 장만 만들어 재사용한다(픽셀을 쓰지 않으므로 1×1 이면 된다). */
let normCanvas: CanvasRenderingContext2D | null | undefined;
function normContext(): CanvasRenderingContext2D | null {
  if (normCanvas === undefined) {
    normCanvas = document.createElement('canvas').getContext('2d');
  }
  return normCanvas;
}

/**
 * **라이브러리에 등록하는 색 파서** — 라이브러리가 못 읽는 색을 픽셀로 재 준다.
 *
 * ── 왜 필요한가 (실측 2026-08-26, 화면이 통째로 에러 경계로 떨어졌다) ────────
 * `lightweight-charts` 는 자기 색 파서를 갖고 있다(가격축 라벨의 대비색을
 * 계산하느라 색을 채널로 뜯는다). 그 파서가 아는 꼴은 hex·`rgb()`·`rgba()`·
 * `hsl()`·`hwb()`·이름뿐이다. 그런데 브라우저의 **계산값**은 그 목록 밖일 수
 * 있다 — `color-mix(in srgb, ...)` 가 크롬에서
 *
 *     color(srgb 0.356863 0.380392 0.431373 / 0.5)
 *
 * 로 계산되고, 캔버스의 `strokeStyle` 은 그걸 읽지만 라이브러리는
 * `Failed to parse color` 로 **던진다**. 색 하나 때문에 커브 전체가
 * «이 종목의 차트를 그리지 못했어요» 로 떨어졌다
 * [OWNER 2026-08-26 — 화면을 보고 알려 줬다].
 *
 * ── 왜 이 방법인가 ──────────────────────────────────────────────────────────
 * 처음에는 팔레트에서 색 문자열을 옛 표기로 되돌려 넘기려 했다. 두 번 틀렸다:
 * 캔버스 `fillStyle` 의 getter 는 `color(srgb ...)` 를 **그대로 돌려주고**,
 * 직접 `rgba(...)` 문자열을 조립하면 이 층이 색을 «만드는» 것이 된다.
 *
 * 라이브러리에 **지원되는 확장점**이 있다(`layout.colorParsers`). 문서가 이
 * 경우를 그대로 적어 뒀다 — «커스텀 파서는 Display P3·Lab·LCH·Oklab·Oklch
 * 같은 다른 색공간에만 필요하다». 파서는 **문자열이 아니라 채널 넷**을
 * 돌려주므로 이 파일에 색 리터럴이 생기지 않고, CDS 가 언젠가 토큰을
 * `oklch()` 로 바꿔도 그대로 버틴다.
 *
 * 재는 방법은 «한 픽셀 칠하고 그 픽셀 읽기» 다. 브라우저가 최종 채널값을
 * 내주고 우리는 받아 적을 뿐이라 색 산술이 없다.
 */
/* 캔버스가 아예 없는 환경(jsdom)의 중립 채널.
 *
 * 이건 «색을 지어내는 것» 이 아니다 — 그 환경에는 **그릴 화면이 없다**. 그런데
 * 라이브러리가 색을 못 읽으면 던지고, 그러면 이 차트를 품은 컴포넌트를 렌더하는
 * **테스트 전체가 멈춘다**(실측 2026-08-26: `Failed to parse color: canvastext`
 * — jsdom 의 `getComputedStyle(el).color` 가 그 시스템 키워드를 준다).
 * 브라우저에는 이 경로가 없다: 거기서는 `getContext('2d')` 가 항상 있다. */
const NO_CANVAS: Rgba = [128, 128, 128, 1] as Rgba;

export const pixelColorParser: CustomColorParser = (color) => {
  const ctx = normContext();
  if (!ctx) return NO_CANVAS;
  if (!color) return null;

  /* 못 읽는 값이면 `fillStyle` 이 조용히 이전 값을 유지한다 — 서로 다른 두
     씨앗으로 두 번 시켜 결과가 같을 때만 «읽혔다» 고 본다. 씨앗은 색이 아니라
     판별용이고 화면에 안 칠해진다. */
  ctx.fillStyle = 'black';
  ctx.fillStyle = color;
  const first = ctx.fillStyle;
  ctx.fillStyle = 'white';
  ctx.fillStyle = color;
  if (ctx.fillStyle !== first) return null;

  ctx.clearRect(0, 0, 1, 1);
  ctx.fillRect(0, 0, 1, 1);
  const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
  /* `Rgba` 는 채널마다 브랜드 타입(`RedComponent` 등)이라 평범한 `number` 가
     안 들어간다. 값은 이미 0~255 / 0~1 범위라 검사할 것이 없어 그대로 못 박는다. */
  return [r, g, b, a / 255] as Rgba;
};

/** 그 엘리먼트가 상속받은 계산값으로 팔레트를 읽는다.
 *
 * ── 못 읽었을 때 ────────────────────────────────────────────────────────────
 * 폴백은 **그 엘리먼트의 글자색**(`cs.color`)이다. 회색 하나를 여기 적어 두는
 * 판을 먼저 썼는데 `guards/color-source.test.ts` 가 잡았고, 그게 옳다 — 이
 * 리포의 색 리터럴은 `direction.css` 한 곳에만 산다. 그리고 규칙을 지키는 쪽이
 * 실제로 더 낫다:
 *
 *   · `cs.color` 는 **언제나 있다**(계산값이라 상속으로라도 채워진다).
 *   · 테마를 따라간다 — 회색 상수와 달리 다크에서도 읽힌다.
 *   · 그런데 **틀린 것이 눈에 띈다**: 토큰이 빠지면 주선·기준선·면이 전부
 *     글자색 한 가지로 그려져 «색이 죽었다» 는 사실이 화면에 그대로 보인다.
 *     그럴듯한 색을 넣으면 다리가 끊어진 줄 아무도 모른다.
 */
export function readPalette(el: Element): LwPalette {
  const cs = getComputedStyle(el);
  const fallback = cs.color;
  const out = {} as LwPalette;
  for (const key of Object.keys(VARS) as ColorKey[]) {
    const v = cs.getPropertyValue(VARS[key]).trim();
    out[key] = v || fallback;
  }
  /* 변수가 아니라 **계산된 상속값**이다 — `--sr-font-sans` 를 읽으면 폴백
     사슬의 원문이 오지만, `font-family` 를 읽으면 이 엘리먼트가 실제로 쓰는
     사슬이 온다. 캔버스에 넘길 것은 후자다. */
  out.fontFamily = cs.fontFamily || 'sans-serif';
  out.fgMutedSoft = soften(el, out.fgMuted, 50);
  /* 프로브는 **이 엘리먼트 안에** 선다 — 상속으로 `--sr-*`·`--color-*` 가
     전부 보이는 자리라야 `var(...)` 가 풀린다. */
  out.resolve = (css: string) => computeColor(el, css) || fallback;
  out.dim = (css: string, percent: number) => soften(el, css, percent);
  return out;
}

/**
 * 차트가 선 엘리먼트의 팔레트. **스킴이 바뀌면 다시 읽는다.**
 *
 * `el` 이 아직 `null` 인 첫 렌더에서는 `null` 을 준다 — 그때 그리면 안 된다는
 * 뜻이고, 호출부는 그 사실로 마운트를 미룬다(색 없이 그린 프레임이 한 장
 * 스치는 것보다 낫다).
 */
export function useLwPalette(el: Element | null): LwPalette | null {
  const { scheme } = useScheme();
  const [palette, setPalette] = useState<LwPalette | null>(null);

  useEffect(() => {
    if (!el) return;
    /* 효과는 DOM 갱신 **뒤에** 돈다 — CDS 가 인라인 변수를 새 스킴으로 바꾼
       다음이라 여기서 읽은 값이 곧 화면의 값이다. */
    setPalette(readPalette(el));
  }, [el, scheme]);

  return palette;
}
