import { describe, expect, it } from 'vitest';

import type { PxHist } from '@/lib/api';
import { SESSION, buildTape, collapseToday, epochOf, midOf, spanDays } from '@/lib/pxTape';

/**
 * 시세 테이프의 규칙 — `lib/pxTape.ts` 의 순수 함수.
 *
 * 틀려도 화면이 멀쩡해 보이는 것들이라 기계가 잰다:
 *   · 분 안에서는 나중 것이 지금
 *   · 호가는 그날 안에서만 서 있다(끌고 가되, 날을 넘기지 않는다)
 *   · 오늘의 끝은 지금을 5분 단위로 올린 자리 — 밤은 자리가 없다
 *   · 체결은 오늘 구간에서만
 *   · 이력에 오늘이 섞여 있으면 라이브가 이긴다
 */

const hist = (days: string[], q: (number | null)[][], mp: (number | null)[]): PxHist => ({ code: '26-1', days, q, mp, asof: days[days.length - 1] ?? null, note: null });
const todayOf = (ymd: string, rows: { m: number; b: number | null; a: number | null }[], nowSec: number, fills: { t: number; y: number; a?: number | null; d?: string | null }[] = []) => ({
  ymd,
  rows,
  mp: 3.945,
  fills: fills.map((f) => ({ t: f.t, y: f.y, a: f.a ?? null, d: f.d ?? null })),
  nowSec,
});

describe('분 접기 — 나중 것이 지금', () => {
  it('같은 분의 두 표본은 뒤의 것이 남고, 없는 쪽은 그대로 둔다', () => {
    const rows = collapseToday([
      { t: 36005, mid: null, b: 3.95, a: 3.94 },
      { t: 36040, mid: null, b: 3.955, a: null },
      { t: 36070, mid: null, b: null, a: 3.93 },
    ]);
    expect(rows).toEqual([
      { m: 600, b: 3.955, a: 3.94 },
      { m: 601, b: null, a: 3.93 },
    ]);
  });
});

describe('테이프 — 자리와 끌고 가기', () => {
  it('★호가는 그날 안에서만 서 있다 — 날이 바뀌면 첫 호가 앞은 비어 있다', () => {
    const h = hist(['2026-09-29', '2026-09-30'], [[0, 600, 3.97, 3.96], [1, 700, 3.95, null]], [3.97, 3.945]);
    const t = buildTape({ hist: h, today: null, days: null });
    const dayLen = SESSION.m1 - SESSION.m0;
    expect(t.days).toEqual(['2026-09-29', '2026-09-30']);
    expect(t.times.length).toBe(dayLen * 2);
    /* 09-29: 10:00 앞은 비고, 10:00 부터 끝까지 서 있다 */
    const i1000 = 600 - SESSION.m0;
    expect(t.bid[i1000 - 1]).toBeNull();
    expect(t.bid[i1000]).toBe(3.97);
    expect(t.bid[dayLen - 1]).toBe(3.97);
    expect(t.ask[dayLen - 1]).toBe(3.96);
    /* 09-30: 첫 자리는 비어 있다 — 어제 저녁 호가가 오늘 아침에 서 있지 않다 */
    expect(t.bid[dayLen]).toBeNull();
    expect(t.ask[dayLen]).toBeNull();
    const i1140 = dayLen + 700 - SESSION.m0;
    expect(t.bid[i1140]).toBe(3.95);
    expect(t.ask[i1140]).toBeNull();
    /* 민평은 그날 내내 같은 값 */
    expect(t.mp[0]).toBe(3.97);
    expect(t.mp[dayLen]).toBe(3.945);
    expect(t.mp[t.mp.length - 1]).toBe(3.945);
  });

  it('자리의 시각은 그날 00:00(KST 벽시계를 UTC 로) + 분', () => {
    const h = hist(['2026-09-30'], [[0, 600, 3.95, 3.94]], [3.945]);
    const t = buildTape({ hist: h, today: null, days: null });
    expect(t.times[0]).toBe(epochOf('2026-09-30') + SESSION.m0 * 60);
    expect(epochOf('2026-09-30')).toBe(Date.UTC(2026, 8, 30) / 1000);
  });

  it('오늘의 끝은 지금을 5분으로 올린 자리이고, 장 끝을 넘지 않는다', () => {
    const today = todayOf('2026-10-01', [{ m: 600, b: 3.95, a: 3.94 }], 13 * 3600 + 40 * 60 + 25);
    const t = buildTape({ hist: null, today, days: 1 });
    /* 13:40:25 → 13:41 → 올려서 13:45 (exclusive) */
    expect(t.mi[t.mi.length - 1]).toBe(13 * 60 + 44);
    expect(t.todayFrom).toBe(0);
    const late = buildTape({ hist: null, today: todayOf('2026-10-01', [{ m: 600, b: 3.95, a: 3.94 }], 17 * 3600 + 30 * 60), days: 1 });
    expect(late.mi[late.mi.length - 1]).toBe(SESSION.m1 - 1);
  });

  it('구간은 오늘을 포함한 마지막 n 영업일', () => {
    const h = hist(['2026-09-26', '2026-09-29', '2026-09-30'], [[0, 600, 3.9, 3.89], [1, 600, 3.91, 3.9], [2, 600, 3.92, 3.91]], [3.9, 3.91, 3.92]);
    const today = todayOf('2026-10-01', [{ m: 600, b: 3.95, a: 3.94 }], 36000);
    expect(buildTape({ hist: h, today, days: 2 }).days).toEqual(['2026-09-30', '2026-10-01']);
    expect(buildTape({ hist: h, today, days: null }).days).toHaveLength(4);
    expect(spanDays('1w')).toBe(5);
    expect(spanDays('all')).toBeNull();
  });

  it('★이력에 오늘이 섞여 있으면 라이브가 이긴다', () => {
    const h = hist(['2026-09-30', '2026-10-01'], [[0, 600, 3.9, 3.89], [1, 600, 1.0, 1.0]], [3.9, 1.0]);
    const today = todayOf('2026-10-01', [{ m: 600, b: 3.95, a: 3.94 }], 36000);
    const t = buildTape({ hist: h, today, days: null });
    expect(t.days).toEqual(['2026-09-30', '2026-10-01']);
    expect(t.bid[t.todayFrom + 600 - SESSION.m0]).toBe(3.95);
    expect(t.mp[t.todayFrom]).toBe(3.945);
  });
});

describe('체결 — 오늘 구간에서만', () => {
  const fills = [{ t: 48331, y: 3.94, a: 100, d: 'DS' }];
  const today = todayOf('2026-10-01', [{ m: 600, b: 3.95, a: 3.94 }], 50000, fills);
  const h = hist(['2026-09-30'], [[0, 600, 3.9, 3.89]], [3.9]);

  it('오늘 구간에서는 그 분 자리에 선다', () => {
    const t = buildTape({ hist: null, today, days: 1 });
    expect(t.fills).toHaveLength(1);
    expect(t.mi[t.fills[0]!.index]).toBe(Math.floor(48331 / 60));
    expect(t.fills[0]).toMatchObject({ y: 3.94, a: 100, d: 'DS', t: 48331 });
  });

  it('긴 구간에서는 싣지 않는다 — 민평 점선이 그 자리를 맡는다', () => {
    expect(buildTape({ hist: h, today, days: 5 }).fills).toEqual([]);
    expect(buildTape({ hist: h, today, days: null }).fills).toEqual([]);
  });
});

describe('가운데', () => {
  it('둘 다 있을 때만 — 한쪽만 서 있으면 가운데가 없다', () => {
    expect(midOf(3.95, 3.94)).toBeCloseTo(3.945);
    expect(midOf(3.95, null)).toBeNull();
    expect(midOf(null, null)).toBeNull();
  });
});
