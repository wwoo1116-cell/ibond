'use client';

/**
 * 시세 — 매도·매수 테이프와 체결 점. [OWNER 2026-10-01 「비드·애스크만 그리고 체결은 표시만.
 * 현재가는 늘 우측, 과거는 옆으로. 어제자랑 이어서 최대 1년.」]
 *
 * ── 09-28 판과 무엇이 다른가 ───────────────────────────────────────────────
 * 그 판은 **오늘** 의 mid·매도·매수 셋을 10초 격자에 그렸다. 이 판은 **매도·매수 둘**을
 * 1분 계단으로 그리고, 어제까지(`/api/px_hist`)와 오늘(`/api/view` 의 `px`)을 한 줄로
 * 잇는다(`lib/pxTape.ts`). mid 선과 바닥 활동 띠는 걷었다 — 둘 다 「값」이 아니라
 * 「둘의 가운데」와 「건수 그림」이었고, 오너가 둘 다 안 보기로 했다.
 *
 * ── 캐논에서 벗어나는 자리 (CLAUDE.md 캐논 규칙 3: 왜인지 적는다) ────────────
 * ① **세로 범위는 자료가 정한다** — 09-03 의 「전일 민평이 정중앙」을 걷는다. 하루치면
 *    대칭이 뜻이 있었지만 한 달을 이으면 민평도 움직이고, 고정 범위는 보이는 구간의
 *    2.9bp 를 판의 1/3 에 가둔다. 민평은 «늘 보이는 점선» 으로 남고 중앙은 아니다.
 * ② **마지막 값이 축에 붙는다**(`lastValue`) — 캐논은 리드아웃이 읽는다고 끄는데,
 *    테이프는 «지금» 이 오른쪽 끝이라는 사실이 그림 자체여야 한다(토스·코인베이스·
 *    바이낸스 셋 다 그렇게 한다 — 2026-10-01 비교).
 * ③ **가로축 글자**(`tick`) — 여러 날을 이으면 날과 시각을 둘 다 말해야 한다.
 *    캐논 옵션(격자·눈금 밀도·축 위치)은 그대로다.
 * ④ **선 아래 면 없음** 은 그대로이고, 대신 **두 선 사이의 띠**가 있다 — 띠의 폭은
 *    스프레드라는 «있는 양» 이다(선 아래 면의 높이는 없는 양이었다).
 */

import { useMemo, useState } from 'react';

import type { LwPalette } from '@/chart/palette';
import { TimeChart, type TimeBand, type TimeLine, type TimeMarker, type TimeTick } from '@/chart/TimeChart';
import type { PxHist } from '@/lib/api';
import { EMDASH, fmtAxis, fmtBpLevel, fmtBpUnit, fmtHms, fmtTapeAt, fmtTapeDay, fmtTapeHm, fmtYield } from '@/lib/format';
import { buildTape, collapseToday, midOf, spanDays, type Px, type SpanKey } from '@/lib/pxTape';
import { ChartReadoutStrip, slotChars, type StripSlot } from '@/ui/ChartReadoutStrip';
import { useMeasure } from '@/ui/useMeasure';

/* 그림 높이는 **카드가 준다** [2026-09-29 「한 화면」] — `.sr-plot` 이 남는 높이를 먹고
 * 그림은 그 칸을 재서 그린다. 상수는 첫 프레임의 기본값이다(0 으로 그리면 캔버스가 안 선다). */
const PX_H = 236;

/** 위아래 여백 — 같은 값인 것은 «대칭» 때문이 아니라 둘 다 자료가 정한 범위의 숨이기 때문. */
const MARGINS = { top: 0.08, bottom: 0.08 } as const;
/** 체결 점에 값을 다는 상한 — 이보다 많으면 점만. */
const FILL_TEXT_MAX = 6;

export function PxChart({
  px,
  hist,
  span,
  todayYmd,
  nowSec,
}: {
  px: Px;
  /** 어제까지. 오늘 구간이거나 아직 안 왔으면 `null` — 그러면 오늘만 그린다. */
  hist: PxHist | null;
  span: SpanKey;
  todayYmd: string;
  /** 장중 초 — 오늘의 끝(테이프의 오른쪽 끝). */
  nowSec: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const [plotRef, , plotH] = useMeasure<HTMLDivElement>();
  const h = plotH || PX_H;
  const days = spanDays(span);

  const todayRows = useMemo(() => collapseToday(px.pts ?? []), [px.pts]);
  const tape = useMemo(
    () =>
      buildTape({
        hist: days === 1 ? null : hist,
        today: { ymd: todayYmd, rows: todayRows, mp: px.mp ?? null, fills: px.fills ?? [], nowSec },
        days,
      }),
    [hist, days, todayYmd, todayRows, px.mp, px.fills, nowSec],
  );

  /* ── 계열 — 매도·매수 둘과 민평 점선. 잉크는 매매색이다(빨강 매수·파랑 매도, 데스크 관례). */
  const lines = useMemo<TimeLine[]>(
    () => [
      /* ⑤ 축 글자가 **세 자리**다(캐논 `fmtAxis` 는 두 자리) — 꼬리표가 같은 서식을 쓰므로
         두 자리면 3.945 가 「3.94」로 선다. 반 bp 가 사라지는 꼬리표는 현재가가 아니다. */
      /* ★굵기 2 는 **주선의 무게**다 [OWNER 2026-10-01 「선이 너무 얇다」]. 이 리포와 v2 의
         `addLine` 기본값이 둘 다 2 이고, 1 은 **보조선 전용**이다(v2 의 밴드 위·아래·이동평균,
         이 앱의 맥박). 첫 판은 셋 다 1 로 줘서 매도·매수가 «참조선 무게» 로 그려졌다 —
         mid 를 걷어 낸 뒤로 이 둘이 주선인데 옛 판의 보조선 무게를 그대로 들고 있었다. */
      { id: 'bid', values: tape.bid, color: (p) => p.up, width: 2, step: true, lastValue: true, beacon: true, format: fmtYield },
      { id: 'ask', values: tape.ask, color: (p) => p.down, width: 2, step: true, lastValue: true, format: fmtYield },
      /* 민평은 한 단 뒤 — 잉크는 «오늘 호가» 의 몫이다. 참조선이라 굵기는 1 로 남는다. */
      { id: 'mp', values: tape.mp, color: (p) => p.dim(p.fgMuted, 70), width: 1, dash: true, step: true, format: fmtAxis },
    ],
    [tape],
  );
  const band = useMemo<TimeBand>(() => ({ hi: 'bid', lo: 'ask', color: (p: LwPalette) => p.dim(p.fgMuted, 14) }), []);
  /* 체결 — 오늘 구간에서만 `tape.fills` 가 찬다. 제 금리 자리에 잉크 점. 값은 점이 적을
     때만 단다 — 25-4 처럼 하루 수십 건이면 글자가 서로를 덮는다(실측 2026-09-30 리플레이). */
  const markers = useMemo<TimeMarker[]>(() => {
    const label = tape.fills.length <= FILL_TEXT_MAX;
    return tape.fills.map((f) => ({ index: f.index, color: (p) => p.fg, price: f.y, text: label ? fmtYield(f.y) : undefined, size: 1 }));
  }, [tape.fills]);
  /* 가로축 글자 — 하루면 시각, 여러 날이면 **날짜만**.
   *
   * ★여러 날에서 시각 눈금을 비우는 이유 [실측 2026-10-01]: 라이브러리는 눈금마다
   *   «무게»(0 년 · 1 월 · 2 일 · 3 시각)를 주는데, 한 달이면 자리가 1만이 넘어 대부분의
   *   눈금이 날 경계가 아닌 **하루 안**에 떨어진다. 그 자리에 시각을 찍으면 날짜들 사이에
   *   「12:40」 하나가 끼어 서고, 읽는 사람은 그것을 날짜 자리로 읽는다(한 축이 두 단위를
   *   말한다). 비우면 날 경계에 선 눈금만 남는다 — 그게 이 축이 세는 것이다. */
  const tick = useMemo<TimeTick>(
    () =>
      days === 1
        ? { mark: (t) => fmtTapeHm(t), at: (t) => fmtTapeHm(t) }
        : { mark: (t, kind) => (kind <= 2 ? fmtTapeDay(t) : ''), at: (t) => fmtTapeAt(t) },
    [days],
  );

  /* ── 리드아웃 ──────────────────────────────────────────────────────────── */
  const range = useMemo(() => {
    let lo = Infinity;
    let hi = -Infinity;
    for (const v of tape.bid) if (v != null) { if (v < lo) lo = v; if (v > hi) hi = v; }
    for (const v of tape.ask) if (v != null) { if (v < lo) lo = v; if (v > hi) hi = v; }
    return Number.isFinite(lo) ? { lo, hi } : null;
  }, [tape]);

  if (!tape.times.length || !range) {
    return <div className="kb-empty">{px.note ?? '표본이 모자랍니다'}</div>;
  }

  /** 커서가 없으면 **마지막 호가 자리**를 읽는다 — 빈 상태가 없으므로 줄이 안 흔들린다. */
  const at = hover ?? tape.quoted[tape.quoted.length - 1] ?? tape.times.length - 1;
  const b = tape.bid[at] ?? null;
  const a = tape.ask[at] ?? null;
  const mp = tape.mp[at] ?? null;
  /** 스프레드(bp) — 매수 금리 − 매도 금리. 음수면 역전(묵은 한쪽이 서 있는 것). */
  const spread = b != null && a != null ? (b - a) * 100 : null;
  const mid = midOf(b, a);
  const dbp = mid != null && mp != null ? (mid - mp) * 100 : null;
  /** 그 자리까지의 마지막 체결(오늘 구간) — 짚은 날 안에서만. */
  const fill = (() => {
    let f = null;
    for (const x of tape.fills) if (x.index <= at && tape.di[x.index] === tape.di[at]) f = x;
    return f;
  })();

  const chars = slotChars(fmtYield, range.lo, range.hi);
  const slots: StripSlot[] = [
    { key: 'ask', label: '매도', value: fmtYield(a), color: 'var(--sr-down)', chars },
    { key: 'bid', label: '매수', value: fmtYield(b), color: 'var(--sr-up)', chars },
    {
      key: 'spr',
      label: '스프레드',
      value: spread == null ? EMDASH : spread < 0 ? `역전 ${fmtBpLevel(-spread)}bp` : `${fmtBpLevel(spread)}bp`,
      chars: 9,
      drop: 2,
    },
    { key: 'mp', label: '민평', value: fmtYield(mp), color: 'var(--color-fgMuted)', opacity: 0.9, chars, drop: 3 },
  ];
  if (fill) {
    slots.push({ key: 'fill', label: '체결', value: `${fmtYield(fill.y)} ${fmtHms(fill.t)}`, color: 'var(--color-fg)', chars: chars + 9, drop: 1 });
  }

  /* 유휴의 시각은 **마지막 표본의 제 시각**(초까지) — 분 격자에 올리기 전의 것.
     짚으면 그 자리(분)다. 여러 날이면 날짜가 앞에 선다. */
  const lastPt = px.pts?.[px.pts.length - 1];
  const date =
    hover == null && days === 1 && lastPt ? fmtHms(lastPt.t) : days === 1 ? fmtTapeHm(tape.times[at]!) : fmtTapeAt(tape.times[at]!);

  return (
    <div className="kb-plotwrap">
      <ChartReadoutStrip
        date={date}
        slots={slots}
        change={dbp == null ? undefined : { label: '민평 대비', text: fmtBpUnit(dbp), v: dbp }}
      />
      <div className="sr-plot" ref={plotRef}>
        <TimeChart
          times={tape.times}
          lines={lines}
          band={band}
          markers={markers}
          tick={tick}
          margins={MARGINS}
          height={h}
          precision={3}
          onHoverIndex={setHover}
          accessibilityLabel={`시세 테이프. ${tape.days.length}영업일, 호가 ${tape.quoted.length}자리. 화살표 키로 자리를 옮깁니다.`}
          hoverLabel={(i) =>
            `${fmtTapeAt(tape.times[i]!)} 매도 ${tape.ask[i] == null ? EMDASH : fmtYield(tape.ask[i])}` +
            ` 매수 ${tape.bid[i] == null ? EMDASH : fmtYield(tape.bid[i])}` +
            ` 민평 ${tape.mp[i] == null ? EMDASH : fmtYield(tape.mp[i])}`
          }
        />
      </div>
    </div>
  );
}
