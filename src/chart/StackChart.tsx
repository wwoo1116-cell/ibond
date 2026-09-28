'use client';

/**
 * 쌓은 막대 + 선 한 장. [2026-09-28]
 *
 * `TimeChart` 의 자매다 — 같은 `canonOptions`, 같은 팔레트 브리지, 같은 리드아웃
 * 규약을 쓰고 몸통만 다르다. 가른 이유는 **막대의 기하**다: 선은 점을 잇지만
 * 쌓은 막대는 «아래 것 위에» 얹히므로 값을 누적해서 넣어야 한다.
 *
 * ── 왜 커스텀 시리즈가 아닌가 ──────────────────────────────────────────────
 * 라이브러리에 «쌓인 히스토그램» 은 없다. 직접 그리는 길(커스텀 시리즈)도 있지만,
 * 그러면 크로스헤어·자동 범위·축 라벨·히트 판정을 **전부 다시 만들어야 한다**
 * (`dottedArea.ts` 머리가 같은 이유로 프리미티브를 골랐다). 대신 재고품
 * `HistogramSeries` 다섯을 **누적값으로, 위에 올 것부터** 얹는다 — 나중에 얹은
 * 것이 앞에 그려지므로 아래 칸이 위 칸을 덮는 그림이 된다. 넷을 공짜로 얻는다.
 *
 * ── 왜 격자가 필요 없나 ────────────────────────────────────────────────────
 * `PxChart` 와 달리 이 차트의 자리는 이미 **고른 묶음**이다(10분). 라이브러리의
 * 인덱스 간격이 그대로 시간 간격이라 공백 격자를 깔 이유가 없다.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { HistogramSeries } from 'lightweight-charts';
import type { HistogramData, ISeriesApi, Time, WhitespaceData } from 'lightweight-charts';

import type { LwPalette } from './palette';
import { addLine, removeLines, type PlacedLine } from './series';
import { sameLines, sameNumbers, sameShape, useStable } from './stable';
import { CROSSHAIR_LABEL_MIN_W } from './metrics';
import { useLwChart } from './useLwChart';
import type { TimeLine } from './TimeChart';

export type Stack = {
  id: string;
  label: string;
  /** `times` 와 같은 길이. 누적은 이 컴포넌트가 한다 — 호출부는 «제 몫» 만 준다. */
  values: readonly number[];
  color: (p: LwPalette) => string;
};

export function StackChart({
  times,
  stacks,
  lines,
  height,
  onHoverIndex,
  accessibilityLabel,
  hoverLabel,
  format,
}: {
  times: readonly number[];
  /** 아래부터 위로. 그리는 차례는 이 컴포넌트가 뒤집는다. */
  stacks: readonly Stack[];
  lines?: readonly TimeLine[];
  height?: number;
  onHoverIndex?: (i: number | null) => void;
  accessibilityLabel: string;
  hoverLabel?: (i: number) => string;
  /** 값 축 눈금 글자. 건수라 정수다. */
  format?: (v: number) => string;
}) {
  const [el, setEl] = useState<HTMLDivElement | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const handle = useLwChart<Time>('time', el);

  const sTimes = useStable(times, sameNumbers);
  const sStackShape = useStable(
    stacks.map((s) => ({ id: s.id, values: s.values as readonly (number | null)[] })),
    sameShape,
  );
  const sStackVals = useStable(
    stacks.map((s) => ({ id: s.id, values: s.values as readonly (number | null)[] })),
    sameLines,
  );
  const sLineShape = useStable(lines ?? [], sameShape);
  const sLineVals = useStable(lines ?? [], sameLines);

  const latest = useRef({ stacks, lines, onHoverIndex, format });
  latest.current = { stacks, lines, onHoverIndex, format };

  const indexOf = useMemo(() => new Map(sTimes.map((t, i) => [String(t), i])), [sTimes]);
  const notify = useCallback((i: number | null) => {
    setHover(i);
    latest.current.onHoverIndex?.(i);
  }, []);

  const barsRef = useRef<ISeriesApi<'Histogram', Time>[] | null>(null);
  const placedRef = useRef<PlacedLine<Time>[] | null>(null);

  /** 누적 — k 번째 막대는 «0..k 의 합» 까지 올라간다. */
  const cum = useCallback((k: number) => {
    const src = latest.current.stacks;
    return sTimes.map((_, i) => {
      let s = 0;
      for (let j = 0; j <= k; j++) s += src[j]?.values[i] ?? 0;
      return s;
    });
  }, [sTimes]);

  useEffect(() => {
    if (!handle || sTimes.length === 0) return;
    const { chart, palette, alive } = handle;
    const src = latest.current;

    chart.applyOptions({
      rightPriceScale: { minimumWidth: CROSSHAIR_LABEL_MIN_W },
    });

    /* ★위에 올 것부터 얹는다 — 나중에 얹은 계열이 앞에 그려지므로, 아래 칸이
       위 칸을 «덮어» 쌓인 그림이 된다. 차례를 뒤집으면 맨 위 칸만 보인다. */
    const bars: ISeriesApi<'Histogram', Time>[] = [];
    for (let k = src.stacks.length - 1; k >= 0; k--) {
      const s = chart.addSeries(HistogramSeries, {
        color: src.stacks[k].color(palette),
        base: 0,
        priceLineVisible: false,
        lastValueVisible: false,
        priceScaleId: 'right',
        priceFormat: { type: 'custom', formatter: src.format ?? ((v: number) => String(Math.round(v))), minMove: 1 },
      });
      const vals = cum(k);
      s.setData(
        sTimes.map((t, i) => ({ time: t as Time, value: vals[i] }) as HistogramData<Time> | WhitespaceData<Time>),
      );
      bars.push(s);
    }
    barsRef.current = bars;

    const placed: PlacedLine<Time>[] = (src.lines ?? []).map((ln) =>
      addLine(
        chart,
        palette,
        {
          id: ln.id,
          color: ln.color,
          width: ln.width,
          dash: ln.dash,
          format: ln.format,
          beacon: ln.beacon ?? false,
          data: sTimes.map((t, i) => {
            const v = ln.values[i];
            return v == null ? { time: t as Time } : { time: t as Time, value: v };
          }),
        },
        0,
      ),
    );
    placedRef.current = placed;

    chart.timeScale().fitContent();
    return () => {
      barsRef.current = null;
      placedRef.current = null;
      if (!alive.current) return;
      for (const s of bars) chart.removeSeries(s);
      removeLines(chart, placed);
    };
  }, [handle, sTimes, sStackShape, sLineShape, cum]);

  /* 값만 갈아 끼운다 — 폴링마다 계열을 안 부순다(`TimeChart` 와 같은 규약). */
  useEffect(() => {
    const bars = barsRef.current;
    const placed = placedRef.current;
    if (!handle || !bars) return;
    const n = latest.current.stacks.length;
    for (let k = n - 1, at = 0; k >= 0; k--, at++) {
      const vals = cum(k);
      bars[at]?.setData(
        sTimes.map((t, i) => ({ time: t as Time, value: vals[i] }) as HistogramData<Time>),
      );
    }
    (latest.current.lines ?? []).forEach((ln, i) => {
      placed?.[i]?.series.setData(
        sTimes.map((t, k) => {
          const v = ln.values[k];
          return v == null ? { time: t as Time } : { time: t as Time, value: v };
        }),
      );
    });
  }, [handle, sTimes, sStackVals, sLineVals, cum]);

  /** 화살표로 짚기 — 값이 있는 묶음만. */
  const sampleIdx = useMemo(
    () => sTimes.map((_, i) => i).filter((i) => stacks.some((s) => (s.values[i] ?? 0) > 0)),
    [sTimes, stacks],
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
        role="application"
        tabIndex={0}
        onKeyDown={onKey}
        aria-label={accessibilityLabel}
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
