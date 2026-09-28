'use client';

/* 주선 아래의 **점무늬 면** — 캐논의 `showArea areaType="dotted"`
 * [OWNER 2026-08-13 — "정말 정말 코인베이스처럼"].
 *
 * ── 왜 직접 그리는가 ────────────────────────────────────────────────────────
 * `lightweight-charts` 의 `AreaSeries` 는 면을 **그라디언트로만** 채운다
 * (`topColor`·`bottomColor` 두 색을 `createLinearGradient` 에 넣는다). 점무늬가
 * 없다. 그래서 이 리포의 면은 라이브러리 밖에서 그린다.
 *
 * ── 왜 커스텀 «시리즈» 가 아니라 «프리미티브» 인가 ──────────────────────────
 * `ICustomSeriesPaneView` 로 시리즈를 새로 만들면 선까지 내가 그려야 하고, 그
 * 순간 크로스헤어 적중·마지막값 라벨·가격축 자동범위·`priceToCoordinate` 를
 * 전부 다시 짜게 된다. 프리미티브는 **평범한 `LineSeries` 에 얹는 붓**이라
 * 그 넷을 라이브러리가 그대로 진다. 면은 장식이지 계열이 아니다 —
 * 그 사실을 구조로 적는다.
 *
 * ── 비트맵 좌표계로 그리는 이유 ─────────────────────────────────────────────
 * 점은 1~2px 짜리다. 미디어 좌표(CSS 픽셀)로 그리면 레티나에서 브라우저가
 * 확대하며 뭉갠다. `useBitmapCoordinateSpace` 는 장치 픽셀을 그대로 주므로
 * 타일을 장치 픽셀로 만들어 붙인다 — 그래서 `PATTERN` 캐시 키에 픽셀비가
 * 들어간다.
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
/* `CanvasRenderingTarget2D` 는 `fancy-canvas` 것인데 그 패키지는
   `lightweight-charts` 의 **전이 의존**이라 pnpm 의 엄격한 node_modules 에서
   직접 임포트되지 않는다. 타입 하나 때문에 의존을 새로 달지 않고, 라이브러리가
   이미 내보낸 시그니처에서 뽑아 쓴다 — 버전이 올라가도 따라온다. */
type CanvasRenderingTarget2D = Parameters<IPrimitivePaneRenderer['draw']>[0];

/** 점 간격·반지름(장치 픽셀 기준 1배). CDS 차트가 쓰던 점무늬와 같은 리듬이다. */
const DOT_GAP = 4;
const DOT_R = 0.75;

/** 타일 캐시 — 색·픽셀비마다 하나. 매 프레임 오프스크린 캔버스를 만들면
 *  스크러버를 끌 때마다 GC 가 튄다. */
const PATTERN = new Map<string, CanvasPattern | null>();

function dotPattern(
  ctx: CanvasRenderingContext2D,
  color: string,
  ratio: number,
): CanvasPattern | null {
  const key = `${color}@${ratio}`;
  const hit = PATTERN.get(key);
  if (hit !== undefined) return hit;

  const size = Math.max(1, Math.round(DOT_GAP * ratio));
  const tile = document.createElement('canvas');
  tile.width = size;
  tile.height = size;
  const tc = tile.getContext('2d');
  let made: CanvasPattern | null = null;
  if (tc) {
    tc.fillStyle = color;
    tc.beginPath();
    tc.arc(size / 2, size / 2, Math.max(0.5, DOT_R * ratio), 0, Math.PI * 2);
    tc.fill();
    made = ctx.createPattern(tile, 'repeat');
  }
  PATTERN.set(key, made);
  return made;
}

/** 면을 채우는 두 방식.
 *
 *  `dots`   캐논의 `areaType="dotted"` — 시계열·커브의 주선이 쓴다.
 *  `solid`  CDS 의 `showArea`(무늬 없음) — 손익 차트가 쓴다. 반투명 한 겹이라
 *           색은 호출부가 이미 흐리게 만들어 넘긴다(`palette.dim`).
 */
export type AreaFill = 'dots' | 'solid';

export type AreaPoint<H = Time> = { time: H; value: number | null };

type Host<H> = {
  chart: SeriesAttachedParameter<H>['chart'] | null;
  series: ISeriesApi<'Line', H> | null;
};

class DottedAreaRenderer<H> implements IPrimitivePaneRenderer {
  constructor(
    private readonly host: Host<H>,
    private readonly points: readonly AreaPoint<H>[],
    private readonly color: string | null,
    private readonly fill: AreaFill,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    const { chart, series } = this.host;
    /* **색이 없으면 안 그린다** — 기본색을 하나 적어 두면 그것이 색 리터럴이
       되고(`guards/color-source.test.ts`), 무엇보다 «색을 아직 안 준 상태» 와
       «이 색으로 그려라» 가 구분되지 않는다. */
    if (!chart || !series || !this.color || this.points.length === 0) return;

    const ts = chart.timeScale();

    target.useBitmapCoordinateSpace((scope) => {
      const { context: ctx, horizontalPixelRatio: hr, verticalPixelRatio: vr } = scope;
      const paint =
        this.fill === 'solid'
          ? (this.color as string)
          : dotPattern(ctx, this.color as string, vr);
      if (!paint) return;

      /* 면의 밑변은 **패널 바닥**이다. 0 선이 아니다 — 이 제품의 세로축은
         금리·스프레드라 0 이 화면 밖인 경우가 대부분이고, 그때 0 을 밑변으로
         잡으면 면이 통째로 사라진다(CDS 차트도 바닥을 썼다). */
      const floor = scope.bitmapSize.height;

      ctx.save();
      ctx.beginPath();

      let open = false;
      let firstX = 0;
      let lastX = 0;

      for (const p of this.points) {
        if (p.value == null) continue;
        const xm = ts.timeToCoordinate(p.time);
        const ym = series.priceToCoordinate(p.value);
        /* 화면 밖 점은 변환기가 `null` 을 준다 — 건너뛴다. 이걸 0 으로 두면
           면이 좌상단으로 무너진다. */
        if (xm == null || ym == null) continue;
        const x = xm * hr;
        const y = ym * vr;
        if (!open) {
          firstX = x;
          ctx.moveTo(x, y);
          open = true;
        } else {
          ctx.lineTo(x, y);
        }
        lastX = x;
      }

      if (!open) {
        ctx.restore();
        return;
      }

      ctx.lineTo(lastX, floor);
      ctx.lineTo(firstX, floor);
      ctx.closePath();
      ctx.fillStyle = paint;
      ctx.fill();
      ctx.restore();
    });
  }
}

/**
 * `LineSeries` 에 붙이는 점무늬 면.
 *
 * 데이터와 색은 **바깥이 준다**(`update`) — 프리미티브가 시리즈의 데이터를
 * 되읽을 수도 있지만, 그러면 호출부가 가진 것과 두 벌이 되고 한쪽만 낡는다.
 */
export class DottedArea<H = Time> implements ISeriesPrimitive<H> {
  private readonly host: Host<H> = { chart: null, series: null };
  private points: readonly AreaPoint<H>[] = [];
  /** `update` 전까지는 **색이 없다** — 그동안은 안 그린다(위 렌더러 주석). */
  private color: string | null = null;
  private fill: AreaFill = 'dots';
  private requestUpdate?: () => void;

  private readonly view: IPrimitivePaneView = {
    /* 면은 **선 아래**다 — `'normal'` 로 두면 주선을 덮는다. */
    zOrder: (): PrimitivePaneViewZOrder => 'bottom',
    renderer: (): IPrimitivePaneRenderer =>
      new DottedAreaRenderer(this.host, this.points, this.color, this.fill),
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

  update(points: readonly AreaPoint<H>[], color: string, fill: AreaFill = 'dots'): void {
    this.points = points;
    this.color = color;
    this.fill = fill;
    this.requestUpdate?.();
  }

  /** 색만 갈아입는다 — 점은 그대로. 겉모습 이펙트가 쓴다(`chart/stable.ts`):
   *  색이 바뀌었다고 계열을 다시 세우면 크로스헤어가 끊긴다. */
  setColor(color: string): void {
    if (this.color === color) return;
    this.color = color;
    this.requestUpdate?.();
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return [this.view];
  }
}
