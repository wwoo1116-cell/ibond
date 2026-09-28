'use client';

/**
 * 시세 — 장중 mid·매도·매수 한 장. [2026-09-28, v2 차트 캐논으로 다시 그림]
 *
 * ── 무엇이 «바보 같았나» ───────────────────────────────────────────────────
 * 옛 판(손 SVG)의 y축 눈금은 서버가 준 범위를 **넷으로 나눈 수**였다. 그래서
 * `4.040 · 4.145 · 4.249 · 4.354` 가 찍혔다. 읽는 사람은 눈금을 «자» 로 쓰는데,
 * 자에 4.249 가 적혀 있으면 그건 자가 아니다. 커브가 09-23 에 같은 이유로 고쳐졌고
 * (「눈금은 데이터가 아니라 격자에서 나온다」), 이 차트는 그때 안 고쳐졌다.
 *
 * 이제 눈금은 라이브러리가 «둥근 수» 로 고르고(`tickMarkDensity: 4`), 격자는 아예
 * 없고, 축은 오른쪽에 서고, 커서가 축에 제 자리를 찍는다 — v2 `canonOptions` 그대로.
 *
 * ── 캐논에서 벗어나는 자리 둘 (CLAUDE.md 캐논 규칙 3: 왜인지 적는다) ────────
 * ① **여백이 대칭**이다. 캐논은 위 0.08 / 아래 0.04 인데, 이 차트는 [OWNER 2026-09-03]
 *    「전일 민평이 정중앙」이 규칙이라 위아래가 같아야 가운데가 진짜 가운데가 된다.
 *    (아래는 활동 띠만큼 더 준다 — 띠는 그림이지 값이 아니다.)
 * ② **주선이 잉크**다. v2 의 주선은 «보이는 구간 순변화의 방향색» 인데, 이 화면에서
 *    빨강·파랑은 이미 «매수·매도» 라는 다른 뜻을 지고 있다(데스크 관례, 09-03).
 *    같은 두 색이 한 그림에서 두 뜻을 말하면 둘 다 안 읽힌다.
 * ③ **선 아래 면(`area: 'dots'`)을 안 그린다.** 면의 높이는 «구간 바닥에서 얼마나
 *    위인가» 인데, 이 차트의 바닥은 민평에서 대칭으로 잡은 수라 아무 뜻이 없다.
 *    그러면 면은 «많다/적다» 로 읽히는 양을 그리는 셈이 되고, 그 양은 없는 양이다.
 *    (금리는 쌓이지 않는다 — 면적이 뜻을 가지는 종류의 수가 아니다.)
 */

import { useMemo, useState } from 'react';

import { TimeChart } from '@/chart/TimeChart';
import type { View } from '@/lib/api';
import { EMDASH, fmtAxis, fmtBpUnit, fmtHms, fmtYield } from '@/lib/format';
import { ChartReadoutStrip, slotChars, type StripSlot } from '@/ui/ChartReadoutStrip';

/** 그림 높이. 활동 띠를 안에 품는다. */
const PX_H = 236;
/** 바닥 활동 띠의 높이 — 옛 화면의 `AB` 와 같은 22px. */
const ACT_BAND = 22;

/**
 * 가로축 격자의 칸(초).
 *
 * ★라이브러리의 가로축은 **인덱스 간격**이다 — 넣은 차례대로 같은 폭을 준다.
 *   표본은 10~15초 간격이라 그냥 넣으면 «10초» 와 «5분» 이 같은 폭으로 그려져
 *   시간이 왜곡된다(실측 1,209점 · 평균 17.6초 · 최소 10초).
 *
 *   그래서 고른 격자에 얹고 빈 자리는 공백점으로 둔다. 5초인 이유는 둘이다:
 *   표본 최소 간격이 10초라 **두 표본이 한 칸에 겹치지 않고**, 900px 폭에서
 *   5초는 0.2px 이라 자리 오차가 눈에 안 보인다. 1초 격자(2만 칸)는 같은 그림에
 *   네 배를 쓴다.
 */
const GRID = 5;

/**
 * 격자의 «끝» 을 5분 단위로 올려 잡는다.
 *
 * ★이것이 없으면 폴링(5초)마다 격자 길이가 바뀌고, 길이가 바뀌면 계열을 다시
 *   세워야 한다(`TimeChart` 의 구조 이펙트). 끝을 5분에 맞춰 두면 다시 세우는
 *   일이 다섯 시간에 60번이 아니라 다섯 번이 된다 — 나머지 폴은 값만 갈아 끼운다.
 */
const CHUNK = 300;

type Pt = { t: number; mid?: number | null; a?: number | null; b?: number | null };

export function PxChart({ px }: { px: NonNullable<View['px']> }) {
  const pts = useMemo(() => (px.pts ?? []) as Pt[], [px]);
  const [hover, setHover] = useState<number | null>(null);

  /* ── 격자와 계열 ───────────────────────────────────────────────────────── */
  const grid = useMemo(() => {
    if (pts.length < 2 || px.lo == null || px.hi == null) return null;
    const t0 = Math.floor(Math.min(px.t0 ?? pts[0].t, pts[0].t) / CHUNK) * CHUNK;
    const t1 = Math.ceil(Math.max(px.t1 ?? pts[pts.length - 1].t, pts[pts.length - 1].t) / CHUNK) * CHUNK;
    const n = Math.floor((t1 - t0) / GRID) + 1;
    const times: number[] = new Array(n);
    for (let i = 0; i < n; i++) times[i] = t0 + i * GRID;
    const mid: (number | null)[] = new Array(n).fill(null);
    const ask: (number | null)[] = new Array(n).fill(null);
    const bid: (number | null)[] = new Array(n).fill(null);
    for (const p of pts) {
      const i = Math.round((p.t - t0) / GRID);
      if (i < 0 || i >= n) continue;
      /* 같은 칸에 둘이 오면 나중 것이 이긴다 — 표본 간격(≥10초)이 격자(5초)보다
         넓어 실제로는 안 겹친다. 겹치면 «나중이 지금» 이 맞다. */
      if (p.mid != null) mid[i] = p.mid;
      if (p.a != null) ask[i] = p.a;
      if (p.b != null) bid[i] = p.b;
    }
    /** 값이 하나라도 있는 자리 — 리드아웃과 화살표가 짚는 자리다. */
    const sample: number[] = [];
    for (let i = 0; i < n; i++) if (mid[i] != null || ask[i] != null || bid[i] != null) sample.push(i);
    return { t0, times, mid, ask, bid, sample };
  }, [pts, px.lo, px.hi, px.t0, px.t1]);

  const lines = useMemo(
    () =>
      grid
        ? [
            {
              id: 'mid',
              values: grid.mid,
              color: (p: { fg: string }) => p.fg, // 캐논 이탈 ② — 머리 주석
              width: 2 as const,
              beacon: true,
              format: (v: number) => fmtAxis(v),
            },
            {
              id: 'ask',
              values: grid.ask,
              color: (p: { down: string; dim: (c: string, n: number) => string }) => p.dim(p.down, 65),
              width: 1 as const,
              format: (v: number) => fmtAxis(v),
            },
            {
              id: 'bid',
              values: grid.bid,
              color: (p: { up: string; dim: (c: string, n: number) => string }) => p.dim(p.up, 65),
              width: 1 as const,
              format: (v: number) => fmtAxis(v),
            },
          ]
        : [],
    [grid],
  );

  const priceLines = useMemo(
    () =>
      px.mp != null
        ? [
            {
              value: px.mp,
              /* 참조선은 한 단 뒤 — 잉크는 «오늘 그린 것» 의 몫이다(v2 `dim(…, 90)`). */
              color: (p: { fgMuted: string; dim: (c: string, n: number) => string }) => p.dim(p.fgMuted, 90),
            },
          ]
        : undefined,
    [px.mp],
  );

  const activity = useMemo(() => {
    const bins = (px.act ?? []).map((a) => ({ t: a.t, n: a.n }));
    return bins.length ? { bins, bin: px.bin || 600, band: ACT_BAND } : undefined;
  }, [px.act, px.bin]);

  const yRange = useMemo(
    () => (px.lo != null && px.hi != null ? { min: px.lo, max: px.hi } : undefined),
    [px.lo, px.hi],
  );

  /* ★대칭 여백 — 민평이 정중앙을 지키려면 위아래가 같아야 한다. 아래만 활동 띠
     높이를 더 준다(띠는 값이 아니라 그림이라 값 구간을 안 먹어야 한다). */
  const margins = useMemo(
    () => ({ top: 0.06, bottom: 0.06 + (activity ? (ACT_BAND + 6) / PX_H : 0) }),
    [activity],
  );

  /* ── 리드아웃 ──────────────────────────────────────────────────────────── */
  if (px.note || !grid || !yRange) {
    return <div className="kb-empty">{px.note ?? '표본이 모자랍니다'}</div>;
  }

  /** 커서가 없으면 **마지막 표본**을 읽는다 — 빈 상태가 없으므로 줄이 안 흔들린다. */
  const at = (() => {
    if (hover == null) return grid.sample[grid.sample.length - 1] ?? 0;
    if (grid.mid[hover] != null || grid.ask[hover] != null || grid.bid[hover] != null) return hover;
    /* 공백 격자를 짚었으면 가장 가까운 표본으로 — 커서는 «칸» 이 아니라 «값» 을 묻는다. */
    let best = grid.sample[0] ?? 0;
    let bd = Infinity;
    for (const i of grid.sample) {
      const d = Math.abs(i - hover);
      if (d < bd) {
        bd = d;
        best = i;
      }
    }
    return best;
  })();

  const chars = slotChars(fmtYield, yRange.min, yRange.max);
  const slots: StripSlot[] = [
    { key: 'mid', label: 'mid', value: fmtYield(grid.mid[at]), color: 'var(--color-fg)', chars },
    { key: 'ask', label: '매도', value: fmtYield(grid.ask[at]), color: 'var(--sr-down)', opacity: 0.65, chars, drop: 2 },
    { key: 'bid', label: '매수', value: fmtYield(grid.bid[at]), color: 'var(--sr-up)', opacity: 0.65, chars, drop: 1 },
  ];
  if (px.mp != null) {
    slots.push({ key: 'mp', label: '민평', value: fmtYield(px.mp), color: 'var(--color-fgMuted)', opacity: 0.9, chars, drop: 3 });
  }
  const dbp = grid.mid[at] != null && px.mp != null ? (grid.mid[at]! - px.mp) * 100 : null;

  return (
    <>
      <ChartReadoutStrip
        date={fmtHms(grid.times[at])}
        slots={slots}
        change={dbp == null ? undefined : { label: '민평 대비', text: fmtBpUnit(dbp), v: dbp }}
      />
      <div className="sr-plot" style={{ height: PX_H }}>
        <TimeChart
          times={grid.times}
          lines={lines}
          priceLines={priceLines}
          yRange={yRange}
          margins={margins}
          activity={activity}
          height={PX_H}
          precision={3}
          onHoverIndex={setHover}
          accessibilityLabel={`시세. 표본 ${grid.sample.length}개. 화살표 키로 표본을 옮깁니다.`}
          hoverLabel={(i) =>
            `${fmtHms(grid.times[i])} mid ${grid.mid[i] == null ? EMDASH : fmtYield(grid.mid[i])}` +
            ` 매도 ${grid.ask[i] == null ? EMDASH : fmtYield(grid.ask[i])}` +
            ` 매수 ${grid.bid[i] == null ? EMDASH : fmtYield(grid.bid[i])}`
          }
        />
      </div>
    </>
  );
}
