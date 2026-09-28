'use client';

/* 활동 막대 — 그림 바닥에 눕는 «그 10분에 몇 건» 띠. [2026-09-28]
 *
 * ── 왜 프리미티브인가 ──────────────────────────────────────────────────────
 * 라이브러리에 `HistogramSeries` 가 있지만 여기서는 못 쓴다. 이 차트의 가로축은
 * **5초 격자**라 한 칸이 5초인데, 활동은 **10분 묶음**이다. 히스토그램은 칸
 * 하나에 막대 하나를 그리므로 막대가 격자 한 칸(1/4320 폭 ≈ 0.2px)이 된다.
 * 막대의 폭이 곧 «묶음의 길이» 라는 뜻을 가지려면 `[t, t+bin]` 두 좌표를 직접
 * 재서 그려야 한다.
 *
 * 그리고 이것은 **값 축의 계열이 아니다.** 건수는 금리 축과 아무 상관이 없어서,
 * 계열로 세우면 자동 범위가 그 수에 끌려간다(서버가 정한 민평 대칭 범위가 깨진다).
 * 바닥에 붙은 띠는 제 높이를 스스로 정하는 그림이고, 그래서 프리미티브다.
 *
 * ★높이의 분모는 `max(n)` 이다 — 옛 SVG 판은 분모로 `tot` 를 쓰고 분자로 `n` 을
 *   써서, 두 수가 다른 종목에서 막대가 실제보다 낮게 그려졌다(2026-09-28 발견).
 *   같은 축으로 재지 않은 비율은 비율이 아니다.
 */

import type {
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  PrimitivePaneViewZOrder,
  SeriesAttachedParameter,
  Time,
} from 'lightweight-charts';

type CanvasRenderingTarget2D = Parameters<IPrimitivePaneRenderer['draw']>[0];

export type ActivityBin = { t: number; n: number };

type Host<H> = { chart: SeriesAttachedParameter<H>['chart'] | null };

class ActivityBarsRenderer<H> implements IPrimitivePaneRenderer {
  constructor(
    private readonly host: Host<H>,
    private readonly bins: readonly ActivityBin[],
    private readonly bin: number,
    private readonly band: number,
    private readonly color: string | null,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    const { chart } = this.host;
    if (!chart || !this.color || this.bins.length === 0) return;
    const ts = chart.timeScale();
    const mx = Math.max(1, ...this.bins.map((b) => b.n));

    target.useBitmapCoordinateSpace((scope) => {
      const { context: ctx, horizontalPixelRatio: hr, verticalPixelRatio: vr } = scope;
      ctx.save();
      ctx.fillStyle = this.color as string;
      const bottom = scope.bitmapSize.height;
      for (const b of this.bins) {
        const x0 = ts.timeToCoordinate(b.t as unknown as H);
        const x1 = ts.timeToCoordinate((b.t + this.bin) as unknown as H);
        /* 화면 밖이면 변환기가 `null` 을 준다 — 0 으로 두면 왼쪽 가장자리에
           막대가 쌓인다(`verticalLines.ts` 의 같은 가드). */
        if (x0 == null) continue;
        const left = Math.round(x0 * hr);
        /* 묶음의 끝이 화면 밖이면 폭을 «한 묶음» 으로 어림한다 — 마지막 막대가
           그 이유로 사라지면 «오늘 마지막 10분은 조용했다» 로 읽힌다. */
        const right = x1 == null ? left + Math.round(this.bin * hr) : Math.round(x1 * hr);
        const w = Math.max(Math.round(2 * hr), right - left - Math.round(hr));
        const h = Math.round(((this.band - 4) * b.n) / mx) * vr;
        if (h <= 0) continue;
        ctx.fillRect(left, bottom - h, w, h);
      }
      ctx.restore();
    });
  }
}

export class ActivityBars<H = Time> implements ISeriesPrimitive<H> {
  private readonly host: Host<H> = { chart: null };
  private bins: readonly ActivityBin[] = [];
  private bin = 600;
  private band = 22;
  private color: string | null = null;
  private requestUpdate?: () => void;

  private readonly view: IPrimitivePaneView = {
    /* 선 아래 — 값이 앞이고 «얼마나 시끄러웠나» 는 배경이다. */
    zOrder: (): PrimitivePaneViewZOrder => 'bottom',
    renderer: (): IPrimitivePaneRenderer =>
      new ActivityBarsRenderer(this.host, this.bins, this.bin, this.band, this.color),
  };

  attached(p: SeriesAttachedParameter<H>): void {
    this.host.chart = p.chart;
    this.requestUpdate = p.requestUpdate;
  }

  detached(): void {
    this.host.chart = null;
    this.requestUpdate = undefined;
  }

  update(bins: readonly ActivityBin[], bin: number, band: number, color: string): void {
    this.bins = bins;
    this.bin = bin;
    this.band = band;
    this.color = color;
    this.requestUpdate?.();
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return [this.view];
  }
}
