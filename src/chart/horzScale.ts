'use client';

/* 라이브러리에 우리 가로축을 알려 주는 한 벌 [2026-08-26 이관].
 *
 * ── 왜 축을 직접 정의하는가 ────────────────────────────────────────────────
 * 라이브러리가 기본으로 주는 가로축은 셋이다 — 날짜(`createChart`), 만기 월수
 * (`createYieldCurveChart`), 가격(`createOptionsChart`). 이 앱의 커브·시뮬 축은
 * 그 셋 중 어느 것도 아니다:
 *
 *   커브    자리는 **√만기**여야 한다(선형 월수는 짧은 쪽을 뭉갠다 — 오너 결정).
 *   시뮬    자리는 **경과일**이고 표본이 듬성하다(D+0·D+7·D+30·…).
 *   충격반응 자리는 **분기**다.
 *
 * ── 왜 «값만 바꿔 넣기» 로는 안 되는가 ─────────────────────────────────────
 * 두 가지가 걸린다.
 *
 * ① **자리는 인덱스 간격이다.** 라이브러리의 가로축은 점을 값이 아니라 순서대로
 *    등간격에 세운다. 커브 차트가 «선형 월수» 를 만드는 방법도 매 월마다 빈 점
 *    (whitespace)을 채워 넣는 것이다. 그러니 자리를 값에 비례시키려면 **사이를
 *    빈 점으로 메워야** 한다. 그건 호출부의 일이다.
 *
 * ② **눈금 자리는 «가중치» 가 정한다.** 어느 점에 글자를 세울지는 그 점의
 *    가중치가 정하고, 라이브러리의 기본 축들은 그 가중치를 **값의 배수 관계**로
 *    매긴다(커브 축이면 120·60·36·12·6·3개월). 값을 스케일해 넣으면 그 배수가
 *    아무 뜻도 없어져서, 10Y 가 가장 낮은 가중치를 받아 좁아지면 **제일 먼저
 *    사라지는** 일이 생긴다.
 *
 * 그래서 이 클래스는 **자리·글자·가중치를 전부 호출부에서 받는다.** 라이브러리에
 * 넘기는 것은 «이 자리에 이 글자를 이 무게로» 뿐이고, 그 사이를 메우는 빈 점은
 * 글자도 가중치도 안 받는다.
 */

import type {
  ChartOptionsImpl,
  IHorzScaleBehavior,
  InternalHorzScaleItem,
  InternalHorzScaleItemKey,
  LocalizationOptions,
  Mutable,
  TickMark,
  TickMarkWeightValue,
  TimeMark,
  TimeScalePoint,
} from 'lightweight-charts';

/** 진짜 값이 있는 자리 하나. */
export type ScaleNode = {
  /** 가로 자리(정수). 라이브러리의 가로축은 정수 칸이다. */
  x: number;
  /** 축에 설 글자. */
  label: string;
  /** 좁아질 때 살아남는 순서. 큰 것이 오래 남는다. */
  weight: number;
};

/* 내부 표현은 그냥 숫자다. 라이브러리가 «내부 아이템» 을 불투명 타입으로 두었을
   뿐이라 오갈 때 못 박아 준다 — 라이브러리 자신의 축들도 똑같이 한다. */
const toInternal = (x: number) => x as unknown as InternalHorzScaleItem;
const fromInternal = (i: InternalHorzScaleItem) => i as unknown as number;

export class LabelledHorzScale implements IHorzScaleBehavior<number> {
  private opts!: ChartOptionsImpl<number>;
  /** 자리 → 그 자리의 글자·무게. **우리가 아는 자리만** 들어 있다. */
  private nodes = new Map<number, ScaleNode>();

  /** 어느 자리가 진짜인지 알려 준다. `setData` **전에** 부른다. */
  setNodes(nodes: readonly ScaleNode[]): void {
    this.nodes = new Map(nodes.map((n) => [n.x, n]));
  }

  options(): ChartOptionsImpl<number> {
    return this.opts;
  }

  setOptions(options: ChartOptionsImpl<number>): void {
    this.opts = options;
  }

  preprocessData(): void {
    /* 손볼 것이 없다 — 값은 이미 이 축의 좌표로 들어온다. */
  }

  updateFormatter(options: LocalizationOptions<number>): void {
    if (this.opts) this.opts.localization = options;
  }

  convertHorzItemToInternal(item: number): InternalHorzScaleItem {
    return toInternal(item);
  }

  createConverterToInternalObj(): (item: number) => InternalHorzScaleItem {
    return toInternal;
  }

  key(internalItem: InternalHorzScaleItem | number): InternalHorzScaleItemKey {
    return internalItem as unknown as InternalHorzScaleItemKey;
  }

  cacheKey(internalItem: InternalHorzScaleItem): number {
    return fromInternal(internalItem);
  }

  /** 크로스헤어가 읽는 글자. */
  formatHorzItem(item: InternalHorzScaleItem): string {
    return this.nodes.get(fromInternal(item))?.label ?? '';
  }

  /** 축에 서는 글자. 우리 자리가 아니면 **빈 문자열**이다. */
  formatTickmark(item: TickMark): string {
    return this.nodes.get(fromInternal(item.time))?.label ?? '';
  }

  maxTickMarkWeight(marks: TimeMark[]): TickMarkWeightValue {
    return marks.reduce((a, b) => (b.weight > a.weight ? b : a), marks[0]).weight;
  }

  fillWeightsForPoints(
    sortedTimePoints: readonly Mutable<TimeScalePoint>[],
    startIndex: number,
  ): void {
    for (let i = startIndex; i < sortedTimePoints.length; i++) {
      const node = this.nodes.get(fromInternal(sortedTimePoints[i].time));
      /* 사이를 메우는 빈 점은 **0** — 자리만 만들고 눈금은 안 받는다. */
      sortedTimePoints[i].timeWeight = (node?.weight ?? 0) as TickMarkWeightValue;
    }
  }
}

/**
 * 노드와 그 사이를 **빈 점으로 메운 데이터**를 만든다.
 *
 * 빈 점이 곧 «자리» 다(위 ①). 값이 없는 노드도 같은 빈 점이 되어 선이 끊긴다 —
 * 빼 버리면 선이 이어져서 «그 자리에 값이 있다» 고 거짓말한다(CDS 판의
 * `connectNulls={false}` 가 하던 일).
 */
export function fillWhitespace(
  xs: readonly number[],
  valueAt: (x: number) => number | null | undefined,
  pad: number,
): ({ time: number } | { time: number; value: number })[] {
  if (xs.length === 0) return [];
  const lo = xs[0] - pad;
  const hi = xs[xs.length - 1] + pad;
  const out: ({ time: number } | { time: number; value: number })[] = [];
  for (let x = lo; x <= hi; x++) {
    const v = valueAt(x);
    out.push(v == null ? { time: x } : { time: x, value: v });
  }
  return out;
}

/** 커서가 선 자리에서 **가장 가까운 노드**의 순번. 정확히 일치를 찾으면 안 된다 —
 *  사이가 빈 점으로 촘촘히 메워져 있어 커서는 거의 항상 노드가 아닌 자리에 선다. */
export function nearestIndex(xs: readonly number[], x: number): number | null {
  if (xs.length === 0) return null;
  let best = 0;
  for (let k = 1; k < xs.length; k++) {
    if (Math.abs(xs[k] - x) < Math.abs(xs[best] - x)) best = k;
  }
  return best;
}
