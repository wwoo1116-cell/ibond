'use client';

/**
 * 시장 맥박 — 10분 묶음의 메시지 종류별 건수 + 어제 같은 시각. [2026-09-28]
 *
 * ── 옛 판이 말하던 두 가지 거짓 ────────────────────────────────────────────
 * ① **눈금이 «최댓값의 0·½·1»** 이었다. 그래서 축에 `0 · 47 · 94` 같은 수가 찍혔다.
 *    그건 자가 아니라 그날 자료의 요약이고, 어제와 견줄 수가 없다(어제는 다른
 *    최댓값을 가지니 같은 높이가 다른 건수를 뜻한다).
 * ② **범주를 방향색으로 칠했다** — 호가가 파랑, 체결이 빨강. 이 앱에서 그 두 색은
 *    «매도·매수» 이자 «오름·내림» 이다. 셋째 뜻을 얹으면 세 뜻 다 안 읽힌다.
 *    이제 범주는 참조색 넷(`--sr-ref-*`)과 잉크가 진다 — 방향쌍과 안 겹치고
 *    라이트·다크 쌍이 실측돼 있는 유일한 묶음이다.
 *
 * 범례는 따로 서지 않는다 — 리드아웃 줄이 견본·이름·값을 한 자리에 모은다
 * (v2 §8.5b 「스트립이 범례를 흡수한다」).
 */

import { useMemo, useState } from 'react';

import { StackChart, type Stack } from '@/chart/StackChart';
import type { View } from '@/lib/api';
import { EMDASH, fmtCount, fmtHm } from '@/lib/format';
import { ChartReadoutStrip, slotChars, type StripSlot } from '@/ui/ChartReadoutStrip';

type Pulse = NonNullable<View['pulse']>;
type BinKey = 'q' | 'a' | 'c' | 'i' | 'o';

const PULSE_H = 190;

/**
 * 범주 다섯 — 아래부터 위로.
 *
 * 색은 «뜻» 이 아니라 «가름» 이다. 그래서 방향쌍을 안 쓰고 참조색을 쓴다:
 * 넷은 서로 색상환에서 떨어져 있고(호박·보라·청록·자홍), 라이트·다크 양쪽에서
 * 카드 위 ≈5:1 로 실측돼 있다(`direction.css` 의 그 블록). 다섯째는 잉크의
 * 흐린 단계 — 「기타」라 앞에 나설 이유가 없다.
 */
const CATS: readonly { k: BinKey; label: string; css: string }[] = [
  { k: 'q', label: '호가', css: 'var(--sr-ref-policy)' },
  { k: 'a', label: '관심', css: 'var(--sr-ref-roll)' },
  { k: 'c', label: '체결', css: 'var(--sr-ref-cd)' },
  { k: 'i', label: '문의', css: 'var(--sr-ref-fut)' },
  { k: 'o', label: '기타', css: 'var(--color-fgMuted)' },
];

export function PulseChart({ p }: { p: Pulse }) {
  const [hover, setHover] = useState<number | null>(null);

  const grid = useMemo(() => {
    const bins = p.bins ?? [];
    const prev = p.prev_bins ?? [];
    if (!bins.length && !prev.length) return null;
    const bin = p.bin || 600;
    /* 장 시간을 늘 보여 준다 — 묶음이 몇 개든 축은 08:00~17:00 을 품는다.
       그래야 «오늘은 조용하다» 가 «자료가 적다» 와 구별된다(옛 판의 규약 그대로). */
    const b0 = Math.floor(Math.min(8 * 3600, ...bins.map((b) => b.t), ...prev.map((b) => b.t)) / bin) * bin;
    const b1 = Math.ceil(Math.max(17 * 3600, ...bins.map((b) => b.t + bin), ...prev.map((b) => b.t + bin)) / bin) * bin;
    const n = Math.floor((b1 - b0) / bin);
    const times: number[] = new Array(n);
    for (let i = 0; i < n; i++) times[i] = b0 + i * bin;
    const at = (t: number) => Math.floor((t - b0) / bin);
    const vals: Record<BinKey, number[]> = {
      q: new Array(n).fill(0), a: new Array(n).fill(0), c: new Array(n).fill(0),
      i: new Array(n).fill(0), o: new Array(n).fill(0),
    };
    for (const b of bins) {
      const i = at(b.t);
      if (i < 0 || i >= n) continue;
      for (const { k } of CATS) vals[k][i] += b[k] ?? 0;
    }
    const prevN: (number | null)[] = new Array(n).fill(null);
    for (const b of prev) {
      const i = at(b.t);
      if (i >= 0 && i < n) prevN[i] = b.n;
    }
    const tot = times.map((_, i) => CATS.reduce((s, { k }) => s + vals[k][i], 0));
    return { bin, times, vals, prevN, tot };
  }, [p]);

  const stacks: Stack[] = useMemo(
    () =>
      grid
        ? CATS.map(({ k, label, css }) => ({
            id: k,
            label,
            values: grid.vals[k],
            /* ★캔버스는 `var()` 를 못 읽는다 — 팔레트가 산 DOM 에서 풀어 준다. */
            color: (pal: { resolve: (c: string) => string }) => pal.resolve(css),
          }))
        : [],
    [grid],
  );

  const lines = useMemo(
    () =>
      grid && grid.prevN.some((v) => v != null)
        ? [
            {
              id: 'prev',
              values: grid.prevN,
              color: (pal: { fgMuted: string; dim: (c: string, n: number) => string }) => pal.dim(pal.fgMuted, 90),
              width: 1 as const,
              format: (v: number) => String(Math.round(v)),
            },
          ]
        : undefined,
    [grid],
  );

  if (!grid) return <div className="kb-empty">아직 메시지가 없습니다</div>;

  /** 유휴면 오늘 마지막으로 값이 있던 묶음. */
  const at = (() => {
    if (hover != null) return hover;
    for (let i = grid.tot.length - 1; i >= 0; i--) if (grid.tot[i] > 0) return i;
    return 0;
  })();

  const chars = slotChars((v: number) => String(Math.round(v)), Math.max(...grid.tot, 1));
  const slots: StripSlot[] = CATS.map(({ k, label, css }, n) => ({
    key: k,
    label,
    value: fmtCount(grid.vals[k][at]),
    color: css,
    chars,
    drop: (5 - n) as 1 | 2 | 3 | 4 | 5,
  }));
  slots.push({
    key: 'prev',
    label: '어제',
    value: grid.prevN[at] == null ? EMDASH : fmtCount(grid.prevN[at]!),
    color: 'var(--color-fgMuted)',
    opacity: 0.9,
    chars,
  });

  return (
    <>
      <ChartReadoutStrip date={fmtHm(grid.times[at])} slots={slots} />
      <div className="sr-plot" style={{ height: PULSE_H }}>
        <StackChart
          times={grid.times}
          stacks={stacks}
          lines={lines}
          height={PULSE_H}
          onHoverIndex={setHover}
          format={(v) => String(Math.round(v))}
          accessibilityLabel={`시장 맥박. ${grid.bin / 60}분 묶음 ${grid.times.length}개. 화살표 키로 묶음을 옮깁니다.`}
          hoverLabel={(i) =>
            `${fmtHm(grid.times[i])} ` + CATS.map(({ k, label }) => `${label} ${grid.vals[k][i]}`).join(' ')
          }
        />
      </div>
    </>
  );
}
