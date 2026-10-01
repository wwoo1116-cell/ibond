/**
 * 시세 테이프 — «어제까지»(`/api/px_hist`)와 «오늘»(`/api/view` 의 `px`)을 한 줄로 잇는
 * **순수 함수**. [OWNER 2026-10-01] 「비드·애스크만 그리고 체결은 표시만. 현재가는 늘
 * 우측, 과거는 옆으로. 어제자랑 이어서 최대 1년.」
 *
 * ── 자리의 규칙 ──────────────────────────────────────────────────────────────
 * · 자리는 **장 시간의 1분**이다(08:30~17:00). 밤은 자리가 없어 날이 맞붙고, 호가가
 *   없던 날은 `days` 에 없어 그 날도 없다 — 「최대한 연결」이 그 뜻이다.
 * · 호가는 **다음 호가까지 서 있다**(계단). 그래서 그날 첫 호가 뒤로는 값을 **끌고 간다**.
 *   끌고 가는 것은 그날 안에서만이다 — 어제 저녁 호가가 오늘 아침에 서 있지 않다.
 * · 오늘의 끝은 «지금» 을 5분 단위로 올려 잡는다 — 분마다 자리가 하나 늘면 차트가
 *   틀을 다시 세우는데(`TimeChart` 의 구조 이펙트), 5분이면 하루 100번이 아니라 20번이다.
 * · 체결은 **오늘 구간에서만** 싣는다 [OWNER]. 긴 구간은 민평 점선이 그 자리를 맡는다.
 * · 자리의 시각은 에포크 초이되 **KST 벽시계를 UTC 로 흘린 것** — `lib/format` 의
 *   `fmtTape*` 가 UTC 손잡이로 되읽는다.
 *
 * 컴포넌트에서 뺀 이유: 이 규칙들은 틀려도 화면이 멀쩡해 보인다(선은 어디든 그어진다).
 * 순수 함수면 렌더러 없이 잴 수 있다(`guards/px-tape.test.ts`).
 */
import type { PxHist, View } from './api';

export type Px = NonNullable<View['px']>;
export type PxFill = Px['fills'][number];

export type SpanKey = '1d' | '1w' | '1m' | '3m' | '1y' | 'all';

/** 구간 — **영업일 수**로 자른다(v2 `ChartApp` 과 같은 수: 1M 22 · 3M 66 · 1Y 260). */
export const SPANS: readonly { key: SpanKey; label: string; days: number | null }[] = [
  { key: '1d', label: '오늘', days: 1 },
  { key: '1w', label: '1주', days: 5 },
  { key: '1m', label: '1개월', days: 22 },
  { key: '3m', label: '3개월', days: 66 },
  { key: '1y', label: '1년', days: 260 },
  { key: 'all', label: '전체', days: null },
];

export function spanDays(key: SpanKey): number | null {
  return SPANS.find((s) => s.key === key)?.days ?? null;
}

/** 장 자리 — 분. 원장의 국고 호가가 09시~16시대에 서고 16:30 뒤에도 꼬리가 있다. */
export const SESSION = { m0: 8 * 60 + 30, m1: 17 * 60 } as const;
/** 오늘 끝을 올려 잡는 단위(분). */
export const CHUNK_MIN = 5;

export type MinuteRow = { m: number; b: number | null; a: number | null };

/** 오늘 — **이 PC 의 날짜**. `toISOString` 은 UTC 라 09시 전엔 어제가 된다. */
export function localYmd(now: Date = new Date()): string {
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
}

/** 'YYYY-MM-DD' → 그날 00:00 의 자리(KST 벽시계를 UTC 로). */
export function epochOf(ymd: string): number {
  const [y, mo, d] = ymd.split('-').map(Number);
  return Date.UTC(y, mo - 1, d) / 1000;
}

/** 오늘 10초 표본 → 분 단위. 분 안에서는 **나중 것이 지금**(서버의 분 접기와 같은 규칙). */
export function collapseToday(pts: readonly Px['pts'][number][]): MinuteRow[] {
  const by = new Map<number, MinuteRow>();
  for (const p of pts) {
    const m = Math.floor(p.t / 60);
    const r = by.get(m) ?? { m, b: null, a: null };
    if (p.b != null) r.b = p.b;
    if (p.a != null) r.a = p.a;
    by.set(m, r);
  }
  return [...by.values()].sort((x, y) => x.m - y.m);
}

export type TapeFill = { index: number; t: number; y: number; a: number | null; d: string | null };

export type Tape = {
  /** 보이는 영업일, 오름차순. */
  days: string[];
  /** 자리의 시각(에포크 초). `TimeChart` 의 `times`. */
  times: number[];
  /** 자리 → 날 순번·장중 분. 리드아웃이 되읽는다. */
  di: number[];
  mi: number[];
  /** 끌고 간 매수·매도. 그날 첫 호가 앞은 `null`. */
  bid: (number | null)[];
  ask: (number | null)[];
  /** 그날의 전일 민평 — 하루 내내 같은 값. */
  mp: (number | null)[];
  /** 호가가 **실제로 온** 자리 — 유휴 리드아웃이 마지막 것을 읽는다. */
  quoted: number[];
  /** 오늘 체결(오늘 구간에서만 채운다). */
  fills: TapeFill[];
  /** 오늘이 시작하는 자리. 오늘이 없으면 -1. */
  todayFrom: number;
};

export type TodayInput = {
  ymd: string;
  rows: readonly MinuteRow[];
  mp: number | null;
  fills: readonly PxFill[];
  /** 장중 초 — 오늘의 끝. */
  nowSec: number;
};

const EMPTY: Tape = { days: [], times: [], di: [], mi: [], bid: [], ask: [], mp: [], quoted: [], fills: [], todayFrom: -1 };

/**
 * 어제까지 + 오늘 → 테이프.
 *
 * `days` 가 n 이면 **오늘을 포함해** 마지막 n 영업일. `null` 은 전부.
 * 이력에 오늘 날짜가 섞여 있으면(오후에 구웠을 때) 그 날은 라이브가 이긴다.
 */
export function buildTape(args: { hist: PxHist | null; today: TodayInput | null; days: number | null }): Tape {
  const { hist, today, days } = args;
  const todayYmd = today?.ymd ?? null;

  /* 날 목록 — 이력(오늘 앞)과 오늘 */
  type Day = { ymd: string; rows: MinuteRow[]; mp: number | null; isToday: boolean };
  const list: Day[] = [];
  if (hist) {
    const perDay = new Map<number, MinuteRow[]>();
    for (const q of hist.q) {
      const [di, m, b, a] = q;
      if (di == null || m == null) continue;
      const rows = perDay.get(di) ?? [];
      rows.push({ m, b: b ?? null, a: a ?? null });
      perDay.set(di, rows);
    }
    hist.days.forEach((ymd, di) => {
      if (todayYmd != null && ymd >= todayYmd) return;
      const rows = (perDay.get(di) ?? []).sort((x, y) => x.m - y.m);
      if (!rows.length) return;
      list.push({ ymd, rows, mp: hist.mp[di] ?? null, isToday: false });
    });
    list.sort((x, y) => (x.ymd < y.ymd ? -1 : 1));
  }
  if (today && today.rows.length) {
    list.push({ ymd: today.ymd, rows: [...today.rows].sort((x, y) => x.m - y.m), mp: today.mp, isToday: true });
  }
  const shown = days == null ? list : list.slice(Math.max(0, list.length - days));
  if (!shown.length) return EMPTY;

  const out: Tape = { days: [], times: [], di: [], mi: [], bid: [], ask: [], mp: [], quoted: [], fills: [], todayFrom: -1 };
  shown.forEach((day, di) => {
    out.days.push(day.ymd);
    const base = epochOf(day.ymd);
    let mEnd = SESSION.m1;
    if (day.isToday && today) {
      /* 지금까지만 — 5분 단위로 올려 잡는다. 표본이 그 뒤에 있으면 표본이 이긴다. */
      const nowM = Math.ceil((Math.floor(today.nowSec / 60) + 1) / CHUNK_MIN) * CHUNK_MIN;
      const lastQ = day.rows[day.rows.length - 1]?.m ?? 0;
      mEnd = Math.min(SESSION.m1, Math.max(nowM, lastQ + 1));
    }
    if (day.isToday) out.todayFrom = out.times.length;
    let k = 0;
    let b: number | null = null;
    let a: number | null = null;
    for (let m = SESSION.m0; m < mEnd; m++) {
      /* 이 분의 호가 — 장 자리 앞(08:30 전)에 온 것은 첫 자리에 얹는다. */
      let hit = false;
      while (k < day.rows.length && (day.rows[k]!.m <= m || m === SESSION.m0)) {
        const r = day.rows[k]!;
        if (r.m > m) break;
        if (r.b != null) b = r.b;
        if (r.a != null) a = r.a;
        hit = true;
        k++;
      }
      const i = out.times.length;
      out.times.push(base + m * 60);
      out.di.push(di);
      out.mi.push(m);
      out.bid.push(b);
      out.ask.push(a);
      out.mp.push(day.mp);
      if (hit) out.quoted.push(i);
    }
  });

  /* 체결 — 오늘 구간에서만 [OWNER]. 자리는 그 분. */
  if (days === 1 && today && out.todayFrom >= 0) {
    for (const f of today.fills) {
      if (f.y == null) continue;
      const m = Math.floor(f.t / 60);
      const idx = out.todayFrom + Math.min(Math.max(m, SESSION.m0), SESSION.m1 - 1) - SESSION.m0;
      if (idx >= out.times.length) continue;
      out.fills.push({ index: idx, t: f.t, y: f.y, a: f.a ?? null, d: f.d ?? null });
    }
  }
  return out;
}

/** 매도·매수의 가운데 — 둘 다 있을 때만. 민평 대비를 재는 자리. */
export function midOf(b: number | null, a: number | null): number | null {
  if (b == null || a == null) return null;
  return (a + b) / 2;
}
