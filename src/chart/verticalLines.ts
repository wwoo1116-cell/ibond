'use client';

/* 세로선 몇 개 — CDS `ReferenceLine dataX={…}` 의 자리 [2026-08-26 이관].
 *
 * 쓰는 곳: 전략 실험 창의 z 오실레이터(«여기서 진입했다»).
 *
 * ── 왜 프리미티브인가 ──────────────────────────────────────────────────────
 * 라이브러리에는 세로 상수선이 없다. 가로선은 `createPriceLine` 이 있는데
 * 세로는 대응이 없다 — 시계열 차트에서 «그 시각» 을 긋는 것은 보통 크로스헤어의
 * 일이라고 보기 때문이다. 하지만 이 화면의 세로선은 커서가 아니라 **사실**이다
 * (그 날 실제로 들어갔다). 그래서 직접 긋는다.
 *
 * 마커(구슬·화살표)로 바꾸지 않은 이유: 그건 다른 그림이다. 이 이관은 문법을
 * 옮기는 것이지 고쳐 그리는 것이 아니다.
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

type CanvasRenderingTarget2D = Parameters<IPrimitivePaneRenderer['draw']>[0];

type Host<H> = {
  chart: SeriesAttachedParameter<H>['chart'] | null;
  series: ISeriesApi<'Line', H> | null;
};

class VerticalLinesRenderer<H> implements IPrimitivePaneRenderer {
  constructor(
    private readonly host: Host<H>,
    private readonly at: readonly { time: H; label?: string; color?: string }[],
    private readonly color: string | null,
    private readonly font: string,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    const { chart } = this.host;
    if (!chart || !this.color || this.at.length === 0) return;
    const ts = chart.timeScale();

    target.useBitmapCoordinateSpace((scope) => {
      const { context: ctx, horizontalPixelRatio: hr } = scope;
      ctx.save();
      ctx.lineWidth = Math.max(1, Math.round(hr));
      const vr = scope.verticalPixelRatio;
      ctx.font = `${Math.round(10 * vr)}px ${this.font}`;
      ctx.textBaseline = 'top';
      for (const m of this.at) {
        const x = ts.timeToCoordinate(m.time);
        /* 화면 밖이면 변환기가 `null` 을 준다 — 0 으로 두면 왼쪽 가장자리에
           선이 쌓인다(`dottedArea.ts` 의 같은 가드). */
        if (x == null) continue;
        const px = Math.round(x * hr) + 0.5;
        /* 선마다 제 색 [2026-08-28]. 한 색뿐이던 시절에는 「들어갔다」와
           「나왔다」가 같은 선이었다 — 전략 창의 진입·청산이 그렇게 보였다.
           안 주면 종전 색 그대로다. */
        ctx.strokeStyle = m.color ?? (this.color as string);
        ctx.beginPath();
        ctx.moveTo(px, 0);
        ctx.lineTo(px, scope.bitmapSize.height);
        ctx.stroke();
        /* 라벨은 선 오른쪽 위. 겹침 회피는 **호출부가** 한다 — 근접한 마크를
           미리 합쳐서 준다(`LinkedCharts::markIdx`). 여기서 다시 피하면 두
           곳이 같은 일을 하게 된다. */
        if (m.label) {
          ctx.fillStyle = m.color ?? (this.color as string);
          ctx.fillText(m.label, px + Math.round(3 * hr), Math.round(2 * vr));
        }
      }
      ctx.restore();
    });
  }
}

export class VerticalLines<H = Time> implements ISeriesPrimitive<H> {
  private readonly host: Host<H> = { chart: null, series: null };
  private at: readonly { time: H; label?: string; color?: string }[] = [];
  private font = 'sans-serif';
  private color: string | null = null;
  private requestUpdate?: () => void;

  private readonly view: IPrimitivePaneView = {
    /* 선 아래 — 주선과 크로스헤어가 위여야 한다. */
    zOrder: (): PrimitivePaneViewZOrder => 'bottom',
    renderer: (): IPrimitivePaneRenderer =>
      new VerticalLinesRenderer(this.host, this.at, this.color, this.font),
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

  update(at: readonly { time: H; label?: string; color?: string }[], color: string,
         font: string): void {
    this.at = at;
    this.color = color;
    this.font = font;
    this.requestUpdate?.();
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return [this.view];
  }
}
