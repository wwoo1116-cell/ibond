'use client';

/* 두 선 사이의 띠 — 시세 테이프의 **스프레드**. [2026-10-01]
 *
 * `dottedArea.ts` 의 자매다: 같은 호스트 규약(차트·시리즈를 `attached` 에서 받는다),
 * 같은 «색이 없으면 안 그린다», 같은 `'bottom'` 층. 다른 것은 밑변이다 — 면의 밑변이
 * 패널 바닥이 아니라 **아래 선**이고, 두 선 모두 계단이라 띠의 가장자리도 계단이다.
 *
 * 띠를 라이브러리의 Area 둘로 흉내 내지 않는 이유: 면은 선에서 패널 바닥까지 가므로
 * 「아래 선 아래」를 바탕색으로 덮어야 띠가 남고, 그 덮개가 격자·기준선까지 지운다.
 * 프리미티브 하나가 폴리곤을 그리면 덮을 것이 없다.
 */

import type {
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  PrimitivePaneViewZOrder,
  SeriesAttachedParameter,
  Time,
} from 'lightweight-charts';

/* `CanvasRenderingTarget2D` 는 `fancy-canvas` 것이라 라이브러리가 내보내지 않는다 —
   `dottedArea.ts` 와 같은 길로 렌더러의 시그니처에서 꺼낸다. */
type CanvasRenderingTarget2D = Parameters<IPrimitivePaneRenderer['draw']>[0];

export type BandPoint<H = Time> = { time: H; hi: number | null; lo: number | null };

type Host<H> = {
  chart: SeriesAttachedParameter<H>['chart'] | null;
  series: ISeriesApi<'Line', H> | null;
};

class BandRenderer<H> implements IPrimitivePaneRenderer {
  constructor(
    private readonly host: Host<H>,
    private readonly points: readonly BandPoint<H>[],
    private readonly color: string | null,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    const { chart, series } = this.host;
    if (!chart || !series || !this.color || this.points.length === 0) return;
    const ts = chart.timeScale();

    target.useBitmapCoordinateSpace((scope) => {
      const { context: ctx, horizontalPixelRatio: hr, verticalPixelRatio: vr } = scope;
      ctx.save();
      ctx.fillStyle = this.color as string;

      /* 한 «구간» = 둘 다 값이 있는 연속 자리. 계단이므로 꼭짓점은 (이번 x, 이전 y) →
         (이번 x, 이번 y) 둘이다. 값이 안 바뀌면 꼭짓점을 안 둔다 — 1년이면 자리가
         5만이고, 폴리곤은 값이 바뀐 자리만 알면 된다. */
      let top: number[] = [];
      let bot: number[] = [];
      let lastX = 0;
      let lastHi = NaN;
      let lastLo = NaN;
      const flush = () => {
        if (top.length >= 4) {
          ctx.beginPath();
          ctx.moveTo(top[0]!, top[1]!);
          for (let i = 2; i < top.length; i += 2) ctx.lineTo(top[i]!, top[i + 1]!);
          /* 마지막 자리의 계단을 그 자리까지 닫는다 */
          ctx.lineTo(lastX, lastHi);
          ctx.lineTo(lastX, lastLo);
          for (let i = bot.length - 2; i >= 0; i -= 2) ctx.lineTo(bot[i]!, bot[i + 1]!);
          ctx.closePath();
          ctx.fill();
        }
        top = [];
        bot = [];
      };

      for (const p of this.points) {
        if (p.hi == null || p.lo == null) {
          flush();
          continue;
        }
        const xm = ts.timeToCoordinate(p.time);
        const yh = series.priceToCoordinate(p.hi);
        const yl = series.priceToCoordinate(p.lo);
        if (xm == null || yh == null || yl == null) {
          flush();
          continue;
        }
        const x = xm * hr;
        const hi = yh * vr;
        const lo = yl * vr;
        if (top.length === 0) {
          top.push(x, hi);
          bot.push(x, lo);
        } else if (hi !== lastHi || lo !== lastLo) {
          /* 계단: 이전 높이로 이 x 까지, 그 다음 이 높이로 */
          top.push(x, lastHi, x, hi);
          bot.push(x, lastLo, x, lo);
        }
        lastX = x;
        lastHi = hi;
        lastLo = lo;
      }
      flush();
      ctx.restore();
    });
  }
}

/** `LineSeries` 에 붙이는 두-선 띠. 데이터와 색은 바깥이 준다(`update`). */
export class BandFill<H = Time> implements ISeriesPrimitive<H> {
  private readonly host: Host<H> = { chart: null, series: null };
  private points: readonly BandPoint<H>[] = [];
  private color: string | null = null;
  private requestUpdate?: () => void;

  private readonly view: IPrimitivePaneView = {
    zOrder: (): PrimitivePaneViewZOrder => 'bottom',
    renderer: (): IPrimitivePaneRenderer => new BandRenderer(this.host, this.points, this.color),
  };

  attached(p: SeriesAttachedParameter<H>): void {
    this.host.chart = p.chart;
    this.host.series = p.series as ISeriesApi<'Line', H>;
    this.requestUpdate = p.requestUpdate;
  }

  detached(): void {
    this.host.chart = null;
    this.host.series = null;
    this.requestUpdate = undefined;
  }

  update(points: readonly BandPoint<H>[], color: string): void {
    this.points = points;
    this.color = color;
    this.requestUpdate?.();
  }

  setColor(color: string): void {
    if (this.color === color) return;
    this.color = color;
    this.requestUpdate?.();
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return [this.view];
  }
}
