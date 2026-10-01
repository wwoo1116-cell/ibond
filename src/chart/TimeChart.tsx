'use client';

/* 시계열 한 장 — 아홉 화면이 같이 쓴다 [2026-08-26 이관].
 *
 * 쓰는 곳: Main 미리보기 · 백테스트(짝 차트 둘 포함) · 밴드 · 전략 실험 창 셋 ·
 * rv 추이.
 *
 * ── 왜 커브·숫자축과 몸통이 다른가 ─────────────────────────────────────────
 * 저쪽은 축의 «뜻» 을 우리가 정해야 해서 `IHorzScaleBehavior` 를 직접 짰다.
 * 날짜 축은 다르다 — 라이브러리가 **월·년 경계에 더 큰 무게를 주는** 눈금 규칙을
 * 이미 갖고 있고, 그건 우리가 다시 만들 이유가 없는 좋은 규칙이다.
 *
 * 그리고 걱정할 것이 하나 없다: 라이브러리의 가로축은 **인덱스 간격**이라
 * 주말·휴일이 자리를 차지하지 않는다. CDS 의 범주 축과 같은 간격이 그대로 나온다.
 * 선을 세우는 일은 `series.ts` 가 커브·숫자축과 **공유한다**.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { LineStyle, createSeriesMarkers } from 'lightweight-charts';
import type {
  ISeriesApi,
  ISeriesMarkersPluginApi,
  LineData,
  Time,
  WhitespaceData,
} from 'lightweight-charts';

import { ActivityBars, type ActivityBin } from './activityBars';
import { BandFill } from './bandFill';
import type { AreaFill } from './dottedArea';
import type { LwPalette } from './palette';
import { VerticalLines } from './verticalLines';
import type { ScalePriceLine } from './series';
import { addLine, removeLines, type LineAxis, type PlacedLine } from './series';
import {
  sameLines,
  sameMarkLines,
  sameMarkers,
  sameNumbers,
  samePriceLines,
  sameShape,
  useStable,
} from './stable';
import { CROSSHAIR_LABEL_MIN_W } from './metrics';
import { useLwChart, type TimeAxisText } from './useLwChart';

export type TimeLine = {
  id: string;
  /** `times` 와 **같은 길이**. `null` 은 그 자리에 값이 없다는 뜻이고 선이 끊긴다. */
  values: readonly (number | null)[];
  color: (p: LwPalette) => string;
  width?: 1 | 2;
  dash?: boolean;
  /** 각진 계단 — 기준금리가 쓴다(`series.ts::ChartLine.step`). */
  step?: boolean;
  /** 선 아래 면 — 캐논은 점무늬. 주선에만. */
  area?: AreaFill;
  areaColor?: (p: LwPalette) => string;
  /** 종목은 오른쪽(`main`), 기준선은 왼쪽(`aux`) [OWNER 2026-08-14]. */
  axis?: LineAxis;
  /** 그 축의 눈금 글자. 축마다 다르므로 계열이 진다(`series.ts` 주석). */
  format?: (v: number) => string;
  /** 커서 구슬 — **주선 하나만** 켠다(`series.ts::addLine` 의 그 주석). */
  beacon?: boolean;
  /** 마지막 값을 축에 꼬리표로 — 시세 테이프의 «지금 매도·매수» [OWNER 2026-10-01]. */
  lastValue?: boolean;
};

/** 두 선 사이의 띠 — 시세 테이프의 스프레드(`bandFill.ts`). 선은 `id` 로 가리킨다. */
export type TimeBand = {
  hi: string;
  lo: string;
  color: (p: LwPalette) => string;
};

/** 가로축의 글자 — 캐논은 장중 초(`useLwChart::clockTick`)인데, 여러 날을 잇는
 *  테이프는 날과 시각을 둘 다 말해야 한다. `kind` 는 라이브러리의 눈금 무게
 *  (0 년 · 1 월 · 2 일 · 3 시각 · 4 초). */
export type TimeTick = {
  mark: (t: number, kind: number) => string;
  at: (t: number) => string;
};

/** 세로선의 결 — 색을 직접 주지 않고 **뜻**을 준다(`theme/tint.ts` 의 규율).
 *  `muted` 가 기본이고, `ink` 는 지금 펴 놓은 것, `up`·`down` 은 방향색이다. */
export type MarkLineTone = 'muted' | 'ink' | 'up' | 'down';

/** 보이는 구간의 고·저 같은 표시점. CDS `Point` 의 자리. */
export type TimeMarker = {
  /** `dates` 의 순번. */
  index: number;
  color: (p: LwPalette) => string;
  /** 주면 선 위가 아니라 **그 값 자리**에 선다 — 체결은 호가가 아니라 제 금리에 찍힌다. */
  price?: number;
  /** 점 옆의 글자(체결 금리). 긴 구간에서는 비운다 — 점만으로 족하다. */
  text?: string;
  /** 라이브러리 크기 단위. 고·저 표시점은 0.6, 체결은 1. */
  size?: number;
};

export function TimeChart({
  times,
  lines,
  markers,
  priceLines,
  markLines,
  band,
  tick,
  yRange,
  margins,
  activity,
  syncIndex,
  hideTimeAxis,
  scaleWidth,
  onScaleWidth,
  height,
  onHoverIndex,
  precision = 2,
  accessibilityLabel,
  hoverLabel,
}: {
  /**
   * 가로축의 자리들, **오름차순·중복 없음**. 장중 초(34497 = 09:34:57).
   *
   * ★라이브러리의 가로축은 **인덱스 간격**이다 — 점을 넣은 차례대로 같은 폭을
   *   준다. 그래서 표본이 불규칙한 시각에 찍히면 «10초 간격» 과 «5분 간격» 이
   *   같은 폭으로 그려져 시간이 왜곡된다. 호출부가 **고른 격자**를 만들어
   *   넣고, 값이 없는 자리는 `null` 로 둔다(공백점 → 선이 끊긴다).
   */
  times: readonly number[];
  lines: readonly TimeLine[];
  markers?: readonly TimeMarker[];
  /** 가로로 눕는 상수선 — 손익 차트의 0선. */
  priceLines?: readonly ScalePriceLine[];
  /** 세로로 서는 선들 — «그 날 들어갔다» 같은 **사실**을 긋는다.
   *  CDS `ReferenceLine dataX={…} label={…}` 의 자리. 겹침 회피(근접 마크
   *  합치기)는 **호출부가** 한다 — 라벨을 아는 쪽이 거기다. */
  markLines?: readonly { index: number; label?: string; tone?: MarkLineTone }[];
  /** 두 선 사이의 띠 — 시세 테이프의 스프레드. 위 선의 계열에 매단다. */
  band?: TimeBand;
  /** 가로축 글자를 바꾼다 — 여러 날을 잇는 테이프만 쓴다. 안 주면 캐논(장중 초). */
  tick?: TimeTick;
  /**
   * 값 축의 범위를 **밖에서** 정한다 — 자동 범위를 끈다.
   *
   * ★시세 차트의 세로 범위는 «그리기» 가 아니라 **규칙**이라 서버가 낸다
   *   (전일 민평이 정중앙을 지나는 대칭 구간, [OWNER 2026-09-03]). 자동 범위에
   *   맡기면 그날 호가가 한쪽에 몰린 날 민평이 가운데서 벗어나고, 그러면 같은
   *   그림이 날마다 다른 것을 뜻하게 된다.
   *
   *   계열마다 `autoscaleInfoProvider` 로 실어 보낸다 — 축의 범위는 그 축에 붙은
   *   **모든 계열의 합집합**이라, 한 계열만 고정하면 나머지가 도로 늘린다.
   */
  yRange?: { min: number; max: number };
  /** 값 축의 위·아래 여백(패널 높이의 비율). 캐논은 0.08/0.04 인데, 대칭이어야
   *  하는 차트는 위아래를 같게 줘야 가운데가 진짜 가운데가 된다. */
  margins?: { top: number; bottom: number };
  /** 바닥에 눕는 활동 띠 — 값 축과 무관한 그림이다(`activityBars.ts`). */
  activity?: { bins: readonly ActivityBin[]; bin: number; band: number };
  /**
   * 바깥에서 짚어 주는 자리 — **짝 차트**가 쓴다(백테스트의 위/아래 차트).
   *
   * CDS 판은 `<ReferenceLine dataX={hover.i}>` 로 세로선을 그렸다. 여기서는
   * 라이브러리의 크로스헤어를 그 자리에 세운다 — 커서가 실제로 그 위에 있을
   * 때와 **같은 그림**이라 두 차트가 한 커서를 공유하는 것으로 읽힌다.
   */
  syncIndex?: number | null;
  /**
   * 가로축(날짜 줄)을 감춘다 — **위아래로 쌓인 차트의 위쪽**이 쓴다.
   *
   * CDS 판의 백테스트는 아래 손익 차트에 `<XAxis>` 를 아예 안 뒀고 그 자리에
   * «x 라벨은 위 차트가 진다 — 두 벌이면 같은 날짜가 두 줄로 선다» 라고 적어
   * 두었다. 이관하면서 그 손잡이가 없어져 날짜가 두 줄이 됐다(실측
   * 2026-08-27 백테스트: 같은 세 날짜가 y≈396 과 y≈523 에 두 번).
   */
  hideTimeAxis?: boolean;
  /** 값 축이 **최소한** 차지할 폭. 쌓인 차트들을 같은 폭으로 맞춘다
   *  (`useStackedScales`). */
  scaleWidth?: number;
  /** 이 차트의 값 축이 실제로 먹은 폭 — 쌓인 형제끼리 최대값을 나눈다. */
  onScaleWidth?: (w: number) => void;
  height?: number;
  onHoverIndex?: (i: number | null) => void;
  precision?: number;
  accessibilityLabel: string;
  hoverLabel?: (i: number) => string;
}) {
  const [el, setEl] = useState<HTMLDivElement | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  /* 축 글자 덮개 — **참조가 안정해야** 차트가 안 다시 만들어진다. 함수는 ref 로
     최신 것을 읽고, 객체는 «있다/없다» 가 바뀔 때만 새로 난다. */
  const tickRef = useRef(tick);
  tickRef.current = tick;
  const hasTick = !!tick;
  const axis = useMemo<TimeAxisText | undefined>(
    () =>
      hasTick
        ? { mark: (t, k) => tickRef.current!.mark(t, k), at: (t) => tickRef.current!.at(t) }
        : undefined,
    [hasTick],
  );
  const handle = useLwChart<Time>('time', el, undefined, axis);

  /* ── 프롭은 **내용**으로 본다 [2026-08-27] ───────────────────────────────────
     호출부는 `dates={points.map((p) => p.t)}` 처럼 매 렌더 새 배열을 줘도 된다.
     참조로 비교하던 시절에는 그것이 계열 전체의 파괴·재생성을 불렀고 화면이
     번쩍였다 — 경위와 계측은 `chart/stable.ts` 머리에. */
  const sTimes = useStable(times, sameNumbers);
  const sLines = useStable(lines, sameLines);
  /* ★«틀» 과 «값» 을 따로 본다 [2026-09-28].
     v2 의 화면은 자료가 하루 한 번 바뀌지만 이 앱은 **5초마다** 폴링한다. 구조
     이펙트가 값에 딸려 있으면 폴마다 계열 넷을 부수고 다시 세우게 되고, 그때마다
     크로스헤어가 끊기고 화면이 번쩍인다. 틀이 그대로면 계열은 그냥 두고 값만
     갈아 끼운다(`setData`). */
  const sShape = useStable(lines, sameShape);
  const sMarkers = useStable(markers, sameMarkers);
  const sPriceLines = useStable(priceLines, samePriceLines);
  const sMarkLines = useStable(markLines, sameMarkLines);

  /* 색·서식은 «모양» 이 아니라 안정화 대상이 아니다. 계열을 다시 세우는
     순간에는 **그때의 최신 것**이 쓰여야 하므로 ref 로 읽는다. */
  const latest = useRef({ lines, markers, priceLines, band, onHoverIndex, onScaleWidth });
  latest.current = { lines, markers, priceLines, band, onHoverIndex, onScaleWidth };
  /** 띠의 «틀» — 어느 두 선인가. 색은 겉모습이다. */
  const bandKey = band ? `${band.hi}|${band.lo}` : '';

  /** 시각 -> 순번. 크로스헤어가 주는 것은 시각뿐이다. */
  const indexOf = useMemo(() => new Map(sTimes.map((t, i) => [String(t), i])), [sTimes]);

  /* 콜백도 ref 로 읽는다 — 인라인 화살표를 넘기는 호출부가 있어서(전략 실험
     창 셋), 의존성에 두면 크로스헤어 구독이 렌더마다 붙었다 떨어진다. */
  const notify = useCallback((i: number | null) => {
    setHover(i);
    latest.current.onHoverIndex?.(i);
  }, []);

  /** 왼쪽 축은 **쓸 때만** 선다 — 빈 축이 서면 플롯이 그만큼 좁아진다. */
  const hasAux = useMemo(() => lines.some((l) => l.axis === 'aux'), [lines]);
  useEffect(() => {
    if (!handle) return;
    handle.chart.applyOptions({
      leftPriceScale: {
        visible: hasAux,
        borderVisible: false,
        scaleMargins: { top: 0.08, bottom: 0.04 },
        /* 눈금 글자만 한 칸 더 흐리게 — CDS 판의
           `styles={{ tickLabel: { opacity: 0.65 } }}` 자리다. 이 축은 종목의
           축이 아니라 **배경의 축**이고(기준선 둘이 쓴다), 읽는 사람이 어느
           숫자가 어느 선의 것인지 헷갈리면 안 된다. 이관 때 빠져서 두 축의
           잉크가 같았다 [2026-08-27 수리]. */
        textColor: handle.palette.dim(handle.palette.fgMuted, 65),
      },
    });
  }, [handle, hasAux]);

  /* ── 쌓인 차트의 «픽셀 정렬» [2026-08-27] ───────────────────────────────────
     값 축의 폭은 **그 축 라벨의 폭**으로 정해진다. 백테스트의 두 차트는
     `3.245`(56px)와 `+20원`(50px)이라 플롯이 914 대 920 으로 어긋났다 — 그
     파일의 계약이 «픽셀까지 같다» 인데도. `minimumWidth` 는 라이브러리가 바로
     이 용도로 둔 옵션이다("multiple charts positioned in a vertical stack each
     have an identical price scale width"). 형제 중 가장 넓은 폭을 다 같이 쓴다.

     폭을 재는 것은 `applyOptions` **뒤**여야 하고, 그리기 한 프레임 뒤에야
     확정되므로 rAF 로 한 번 더 잰다. 값이 커지기만 하므로(형제의 최대) 되먹임
     없이 한두 프레임에 수렴한다. */
  useEffect(() => {
    if (!handle) return;
    const { chart } = handle;
    chart.applyOptions({
      /* 바닥이 **둘**이고 큰 쪽이 이긴다 [2026-09-21]. 하나는 형제 차트와 폭을
         맞추는 것(`scaleWidth`), 다른 하나는 크로스헤어 라벨이 잘리지 않게 하는
         것(`CROSSHAIR_LABEL_MIN_W` — 그 수의 유래는 그 상수의 머리글).

         둘을 따로 `applyOptions` 하면 **나중 것이 앞 것을 덮는다** — 같은 키에
         쓰는 것이라 「합쳐진다」가 아니다. 한 줄에서 `Math.max` 로 합치는 이유가
         그것이고, 이 리포가 쌓인 차트에서 이미 한 번 겪은 어긋남이다. */
      rightPriceScale: {
        minimumWidth: Math.max(scaleWidth ?? 0, CROSSHAIR_LABEL_MIN_W),
        ...(margins ? { scaleMargins: margins } : {}),
      },
      timeScale: { visible: !hideTimeAxis },
    });
    const report = () => latest.current.onScaleWidth?.(chart.priceScale('right').width());
    report();
    const id = requestAnimationFrame(report);
    return () => cancelAnimationFrame(id);
  }, [handle, scaleWidth, hideTimeAxis, margins, sTimes, sShape]);

  const markerApi = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  /** 크로스헤어를 세울 계열 — 첫 줄(주선)이다. */
  const anchor = useRef<ISeriesApi<'Line', Time> | null>(null);
  const vlines = useRef<VerticalLines<Time> | null>(null);
  /** 지금 서 있는 계열들 — 겉모습 이펙트가 여기로 색을 갈아입힌다. */
  const placedRef = useRef<PlacedLine<Time>[] | null>(null);
  /** 계열에 **실제로 입혀진** 색. 이것과 다를 때만 다시 입힌다. */
  const inkRef = useRef<string[]>([]);
  /** 짝 차트가 세운 커서가 있는가 — 없는데 지우면 **내 커서**가 지워진다. */
  const syncedRef = useRef(false);

  /* ── 이펙트가 둘인 이유 ─────────────────────────────────────────────────────
     아래는 **구조**다: 계열을 세우고 부순다. 그 아래 «겉모습» 이펙트는 색만
     갈아입힌다. 가른 이유는 색이 바뀌었다고 계열을 부수면 크로스헤어가 끊기고
     화면이 번쩍이기 때문이다(MA 색 취향을 바꾸면 값은 그대로인데 색만 바뀐다). */
  const abars = useRef<ActivityBars<Time> | null>(null);
  /** 띠 — 어느 계열(`at`)에 매달았는지 같이 적어 둔다(떼어 낼 때 그 계열이어야 한다). */
  const bandRef = useRef<{ fill: BandFill<Time>; at: number } | null>(null);

  useEffect(() => {
    if (!handle || sTimes.length === 0) return;
    const { chart, palette, alive } = handle;
    /* 함수는 최신 것 — `sLines` 와 모양이 같으므로 순번이 맞는다. */
    const src = latest.current;

    const placed: PlacedLine<Time>[] = sShape.map((ln, i) =>
      addLine(
        chart,
        palette,
        {
          id: ln.id,
          color: src.lines[i]?.color ?? ln.color,
          width: ln.width,
          dash: ln.dash,
          step: ln.step,
          area: ln.area,
          areaColor: src.lines[i]?.areaColor ?? ln.areaColor,
          axis: ln.axis,
          lastValue: ln.lastValue,
          format: src.lines[i]?.format ?? ln.format,
          /* 아무도 안 켰으면 **첫 줄**이 켠 것으로 친다. 이 리포의 모든 시계열
             차트에서 첫 줄이 주선이고(`anchor` 도 그 규약을 쓴다), 그래야 아홉
             호출부가 한 줄씩 더 적지 않아도 구슬이 하나 남는다. */
          beacon: ln.beacon ?? (sShape.some((l) => l.beacon) ? false : i === 0),
          range: yRange,
          data: sTimes.map((t, k) => {
            const v = src.lines[i]?.values[k] ?? null;
            return (v == null ? { time: t as Time } : { time: t as Time, value: v }) as
              | LineData<Time>
              | WhitespaceData<Time>;
          }),
        },
        precision,
      ),
    );
    placedRef.current = placed;
    /* 방금 입힌 색을 적어 둔다 — 아래 겉모습 이펙트가 곧바로 다시 입히지
       않도록. */
    inkRef.current = sShape.map((ln, i) => (src.lines[i]?.color ?? ln.color)(palette));

    /* 고·저 표시점 — CDS `Point` 자리. 주선(첫 계열)에 매단다.
       값 자리(`price`)를 주면 선이 아니라 그 금리에 선다 — 체결 점. */
    if (sMarkers?.length && placed[0]) {
      markerApi.current = createSeriesMarkers(
        placed[0].series,
        sMarkers
          .filter((m) => sTimes[m.index] != null)
          .map((m, i) => {
            const color = (src.markers?.[i]?.color ?? m.color)(palette);
            const base = { time: sTimes[m.index] as Time, shape: 'circle' as const, color, size: m.size ?? 0.6, text: m.text };
            return m.price != null
              ? { ...base, position: 'atPriceMiddle' as const, price: m.price }
              : { ...base, position: 'inBar' as const };
          }),
      );
    }

    /* 두 선 사이의 띠 — 위 선의 계열에 매단다. 점은 두 선의 값에서 바로 난다. */
    if (src.band) {
      const hi = sShape.findIndex((l) => l.id === src.band!.hi);
      const lo = sShape.findIndex((l) => l.id === src.band!.lo);
      if (hi >= 0 && lo >= 0 && placed[hi]) {
        const bf = new BandFill<Time>();
        placed[hi].series.attachPrimitive(bf);
        bf.update(
          sTimes.map((t, k) => ({ time: t as Time, hi: src.lines[hi]?.values[k] ?? null, lo: src.lines[lo]?.values[k] ?? null })),
          src.band.color(palette),
        );
        bandRef.current = { fill: bf, at: hi };
      }
    }

    /* 가로 상수선. 첫 계열에 매단다 — 값 축이 하나뿐이라 어디 붙어도 같다. */
    (sPriceLines ?? []).forEach((pl, i) => {
      placed[0]?.series.createPriceLine({
        price: pl.value,
        color: (src.priceLines?.[i]?.color ?? pl.color)(palette),
        lineWidth: 1,
        lineStyle: pl.dash ? LineStyle.Dotted : LineStyle.Solid,
        axisLabelVisible: false,
        title: '',
      });
    });

    anchor.current = placed[0]?.series ?? null;

    if (sMarkLines?.length && placed[0]) {
      const v = new VerticalLines<Time>();
      placed[0].series.attachPrimitive(v);
      const tone: Record<MarkLineTone, string> = {
        muted: palette.fgMuted,
        ink: palette.fg,
        up: palette.up,
        down: palette.down,
      };
      v.update(
        sMarkLines
          .filter((m) => sTimes[m.index] != null)
          .map((m) => ({
            time: sTimes[m.index] as Time,
            label: m.label,
            color: m.tone ? tone[m.tone] : undefined,
          })),
        palette.fgMuted,
        palette.fontFamily,
      );
      vlines.current = v;
    }

    /* 활동 띠 — 주선에 매단다. 값 축을 안 쓰므로 어디 붙어도 같다. */
    if (activity && activity.bins.length && placed[0]) {
      const ab = new ActivityBars<Time>();
      placed[0].series.attachPrimitive(ab);
      ab.update(activity.bins, activity.bin, activity.band, palette.dim(palette.fgMuted, 30));
      abars.current = ab;
    }

    chart.timeScale().fitContent();

    return () => {
      /* 차트가 이미 사라졌으면 지울 것이 없다 — `LwHandle.alive` 주석. */
      markerApi.current = null;
      anchor.current = null;
      placedRef.current = null;
      if (alive.current && vlines.current && placed[0]) {
        placed[0].series.detachPrimitive(vlines.current);
      }
      vlines.current = null;
      if (alive.current && abars.current && placed[0]) {
        placed[0].series.detachPrimitive(abars.current);
      }
      abars.current = null;
      const bf = bandRef.current;
      if (alive.current && bf && placed[bf.at]) {
        placed[bf.at]!.series.detachPrimitive(bf.fill);
      }
      bandRef.current = null;
      if (alive.current) removeLines(chart, placed);
    };
  }, [handle, sTimes, sShape, sMarkers, sPriceLines, sMarkLines, precision, yRange, activity, bandKey]);

  /* ── 값만 갈아 끼운다 ───────────────────────────────────────────────────────
     틀이 그대로일 때 도는 이펙트다. 계열을 안 부수므로 크로스헤어가 안 끊기고
     `fitContent` 도 안 부른다(보고 있던 구간이 폴마다 도로 튀지 않게). */
  useEffect(() => {
    const placed = placedRef.current;
    if (!handle || !placed) return;
    sLines.forEach((ln, i) => {
      const p = placed[i];
      if (!p) return;
      p.series.setData(
        sTimes.map((t, k) => {
          const v = ln.values[k];
          return (v == null ? { time: t as Time } : { time: t as Time, value: v }) as
            | LineData<Time>
            | WhitespaceData<Time>;
        }),
      );
    });
    /* 띠도 값이다 — 두 선의 값에서 다시 난다. */
    const bf = bandRef.current;
    const bd = latest.current.band;
    if (bf && bd) {
      const hi = sLines.findIndex((l) => l.id === bd.hi);
      const lo = sLines.findIndex((l) => l.id === bd.lo);
      if (hi >= 0 && lo >= 0) {
        bf.fill.update(
          sTimes.map((t, k) => ({ time: t as Time, hi: sLines[hi]!.values[k] ?? null, lo: sLines[lo]!.values[k] ?? null })),
          bd.color(handle.palette),
        );
      }
    }
  }, [handle, sTimes, sLines]);

  /* 활동 띠도 값이다 — 같은 이유로 따로 갱신한다. */
  useEffect(() => {
    if (!handle || !abars.current || !activity) return;
    abars.current.update(
      activity.bins,
      activity.bin,
      activity.band,
      handle.palette.dim(handle.palette.fgMuted, 30),
    );
  }, [handle, activity]);

  /* ── 겉모습 — 계열을 부수지 않고 색만 갈아입힌다 ───────────────────────────
     값은 그대로인데 색만 바뀌는 자리가 실제로 있다(MA 색 취향). 푼 색이 정말
     달라졌을 때만 `applyOptions` 를 부른다 — 인라인 화살표를 주는 호출부가
     있어서, 함수 참조가 바뀐 것만으로는 아무 일도 하지 않는다. */
  useEffect(() => {
    const placed = placedRef.current;
    if (!handle || !placed) return;
    const { palette } = handle;
    const ink = inkRef.current;
    lines.forEach((ln, i) => {
      const p = placed[i];
      if (!p) return;
      const stroke = ln.color(palette);
      if (ink[i] !== stroke) {
        ink[i] = stroke;
        p.series.applyOptions({ color: stroke });
      }
      if (p.area) p.area.setColor(ln.areaColor ? ln.areaColor(palette) : stroke);
    });
    if (bandRef.current && band) bandRef.current.fill.setColor(band.color(palette));
  }, [handle, lines, band]);

  /* 짝 차트가 짚어 준 자리. 값은 주선의 그날 값을 쓴다 — 크로스헤어는 가로
     자리만 보이면 되지만 API 가 값을 요구한다. */
  useEffect(() => {
    if (!handle) return;
    const { chart } = handle;
    const s = anchor.current;
    const t = syncIndex == null ? null : sTimes[syncIndex];
    const v = syncIndex == null ? null : (sLines[0]?.values[syncIndex] ?? null);
    if (s && t != null && v != null) {
      syncedRef.current = true;
      chart.setCrosshairPosition(v, t as Time, s);
    } else if (syncedRef.current) {
      /* **세운 적이 있을 때만 지운다** [실측 2026-08-27]. 그냥 지우면 커서가
         이 차트 위에 있을 때도 라이브러리가 크로스헤어를 내리고, 그 순간
         빈 이벤트가 날아와 리드아웃 카드가 사라진다. 짝을 안 쓰는 화면
         (Main 미리보기는 `syncIndex` 를 아예 안 넘긴다)에서는 렌더마다
         그 일이 났다 — 번쩍거림의 두 번째 뿌리였다. */
      syncedRef.current = false;
      chart.clearCrosshairPosition();
    }
  }, [handle, syncIndex, sTimes, sLines]);

  /** 화살표로 짚기 — 값이 **있는** 자리만 건너뛴다(공백 격자는 지나친다). */
  const sampleIdx = useMemo(
    () => sTimes.map((_, i) => i).filter((i) => sLines.some((l) => l.values[i] != null)),
    [sTimes, sLines],
  );
  const onKey = useCallback(
    (ev: React.KeyboardEvent<HTMLDivElement>) => {
      if (!sampleIdx.length) return;
      if (ev.key === 'ArrowRight' || ev.key === 'ArrowLeft') {
        ev.preventDefault();
        const d = ev.key === 'ArrowRight' ? 1 : -1;
        const cur = hover == null ? -1 : sampleIdx.indexOf(hover);
        const at = cur < 0 ? (d > 0 ? 0 : sampleIdx.length - 1) : (cur + d + sampleIdx.length) % sampleIdx.length;
        notify(sampleIdx[at]);
      } else if (ev.key === 'Escape') {
        notify(null);
      }
    },
    [sampleIdx, hover, notify],
  );

  useEffect(() => {
    if (!handle) return;
    const { chart } = handle;
    const onMove = (param: { time?: Time }) => {
      const t = param.time;
      notify(t == null ? null : (indexOf.get(String(t)) ?? null));
    };
    chart.subscribeCrosshairMove(onMove);
    return () => chart.unsubscribeCrosshairMove(onMove);
  }, [handle, indexOf, notify]);

  return (
    <>
      <div
        ref={setEl}
        /* ★그림은 **위젯 하나**다 [v2 「키보드와 접근성」 1] — 표본 천 개에
           탭 정지를 천 개 두면 키보드 사용자에게는 함정이 된다. 탭으로 들어와
           화살표로 짚고 `Esc` 로 놓는다. 짚은 것은 아래 `aria-live` 줄이 읽는다. */
        role="application"
        tabIndex={0}
        onKeyDown={onKey}
        aria-label={accessibilityLabel}
        /* **부모가 가로 flex 든 세로 flex 든 맞아야 한다.**
           CDS `Box` 는 flex row, `VStack` 은 flex column 이라 이 div 는 둘 다에
           놓인다. 실측 2026-08-26 에 양쪽으로 한 번씩 틀렸다:
             · 아무 것도 안 주면 가로 부모에서 **폭 0** 이 된다(캔버스는 안에서
               절대 배치라 «내용» 이 없다 — 부모 874px 에 이 div 0px).
             · `flexBasis: 0` 을 주면 세로 부모에서 **높이 0** 이 된다(그 축의
               main-size 가 0 이 되고, 부모에 정해진 높이가 없어 안 자란다).
           `flexBasis: 'auto'` 는 «그 축의 크기 속성을 쓰라» 는 뜻이라 가로에서는
           `width`, 세로에서는 `height` 를 본다. 둘 다 주고 `flexGrow` 로 남는
           자리를 받는다. `minWidth/minHeight: 0` 이 없으면 flex 아이템의 최소
           크기가 내용이라 줄지 않는다. */
        style={{
          flexGrow: 1,
          flexBasis: 'auto',
          minWidth: 0,
          minHeight: 0,
          width: '100%',
          height: height != null ? height : '100%',
        }}
      />
      <span className="sr-a11y-only" aria-live="polite">
        {hoverLabel && hover != null ? hoverLabel(hover) : ''}
      </span>
    </>
  );
}

/**
 * 위아래로 쌓인 차트들이 **같은 값-축 폭**을 쓰게 한다.
 *
 * 돌려주는 둘을 형제 차트마다 그대로 펼쳐 준다:
 *
 *     const stack = useStackedScales();
 *     <TimeChart … {...stack} />
 *     <TimeChart … {...stack} hideTimeAxis={false} />
 *
 * 폭은 형제 중 **가장 넓은 것**으로 수렴한다. 줄어들지 않는 이유는 좁아지는
 * 쪽으로 따라가면 둘이 서로를 밀며 진동하기 때문이다 — 창은 새 실행마다 다시
 * 서므로 한 화면 안에서 단조인 것으로 충분하다.
 */
export function useStackedScales(): {
  scaleWidth: number | undefined;
  onScaleWidth: (w: number) => void;
} {
  const [scaleWidth, setScaleWidth] = useState<number>();
  const onScaleWidth = useCallback(
    (w: number) => setScaleWidth((prev) => (prev == null || w > prev ? w : prev)),
    [],
  );
  return { scaleWidth, onScaleWidth };
}
