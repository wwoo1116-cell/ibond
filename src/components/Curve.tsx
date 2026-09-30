'use client';

/**
 * 잔존 × YTM 산점도. 서버가 준 점과 민평선을 좌표로만 옮긴다.
 *
 * [OWNER 2026-09-23] 「이 부분 너무 바보 같은데 바꿀 방법 없나? 인터렉션도 없고」
 *
 * 무엇이 «바보 같았나» — 두 가지였다.
 *
 * ① ★축 눈금이 «데이터의 최소·중간·최대» 였다. 그래서 y 에 2.99 · 4.38 · 5.77,
 *    x 에 0M · 8.8년 · 17.5년 이 찍혔다. 읽는 사람은 눈금을 «자» 로 쓰는데,
 *    자에 8.8 이 적혀 있으면 그건 자가 아니다. 눈금은 **데이터가 아니라 격자**에서
 *    나와야 한다 — 1 · 2 · 2.5 · 5 × 10^k 로 «둥근 수» 를 고른다(`niceTicks`).
 *    그러면 y 는 3.00·3.50·4.00…, x 는 0·5년·10년… 이 된다.
 * ② ★상호작용이 브라우저 기본 `<title>` 뿐이었다. 1~2초 기다려야 뜨고, 반지름
 *    3px 점을 정확히 맞혀야 하며, 키보드로는 닿지 못한다.
 *    → **가장 가까운 점**을 집는다(조준이 아니라 «근처» 면 된다). 십자선과
 *      말풍선이 따라오고, 화살표 키로도 점을 옮겨 다닌다.
 *
 * ── 2026-09-28: 같은 규율을 **v2 캐논**으로 한 번 더 옮겼다 ────────────────
 * 09-23 판은 이 차트만 고쳤고, 그래서 이 앱 안에서 이 차트만 다른 얼굴이 됐다
 * (여기는 헤어라인 격자·왼쪽 축, 시세와 맥박은 또 각자). 이제 넷이 한 문법이다:
 *   · **격자 없음** — 눈금이 곧 자이고, 격자는 그 자를 그림 위에 복사한 것이다.
 *   · **축은 오른쪽** — 시세·맥박(lightweight-charts 캐논)과 같은 쪽.
 *   · **커서가 축에 제 자리를 찍는다** — 세로 십자선 + 축 칩 둘. 가로선은 안 긋는다
 *     (v2 `canonOptions.crosshair.horzLine.visible: false` 와 같은 판단).
 *   · **x 는 √만기** — 선형 월수는 짧은 쪽을 뭉갠다(`chart/tenorScale.ts`).
 *   · **떠 있는 말풍선을 걷고 그림 밖 한 줄로** [v2 §8.5b, OWNER 2026-09-21] —
 *     말풍선은 그림을 가리고 커서를 피해 다니느라 읽는 동안 글자가 움직였다.
 *     범례도 그 줄이 흡수한다(견본·이름·값이 한 자리).
 *
 * 규율(dataviz)
 *  · 점은 작게, 축은 «뒤로» 물린다.
 *  · 맞히는 영역은 그린 것보다 커야 한다. 여기선 SVG 전체에서 최근접을 재므로
 *    점 하나하나에 히트박스를 안 둔다(조밀 산점도의 표준 처리).
 *  · 말풍선은 **값이 앞, 이름이 뒤** — 읽는 사람은 종목을 이미 알고 수를 원한다.
 *  · 색은 새로 만들지 않고 데스크 규약을 그대로 쓴다 — 매도 파랑(`--sr-down`) ·
 *    매수 빨강(`--sr-up`). 민평 대비 부호를 칠하는 «발산» 쓰임이라 따뜻·차가운
 *    두 극에 중립 회색 가운데라는 규칙에 그대로 맞는다.
 *  · 색만으로 말하지 않는다 — 범례에 글자가 같이 서고, 말풍선이 부호를 적는다.
 */
import { useCallback, useMemo, useRef, useState } from 'react';

import type { View } from '@/lib/api';
import { monthsLabel } from '@/chart/tenor';
import { monthsToX, weightOf } from '@/chart/tenorScale';
import { AXIS_FONT_PX, CROSSHAIR_LABEL_MIN_W, TICK_DENSITY } from '@/chart/metrics';
import { fmtAxis, fmtBpUnit, fmtTtm, fmtYield } from '@/lib/format';
import { ChartReadoutStrip, slotChars, type StripSlot } from '@/ui/ChartReadoutStrip';
import { useMeasure } from '@/ui/useMeasure';


/**
 * x 축 눈금 후보 — **만기 사다리**에서 고른다(`chart/tenorScale.weightOf`).
 *
 * √축에서는 «둥근 수» 가 둥근 자리에 안 온다(5년과 10년의 간격이 1년과 4년의
 * 간격보다 좁다). 그래서 이 축의 눈금은 수가 아니라 **만기**다 — 3M·6M·1Y·2Y·3Y·
 * 5Y·10Y·20Y·30Y·50Y 가 딜러가 실제로 부르는 이름이고, 그게 자의 눈금이어야 한다.
 * 무게가 큰 것부터 넣되 이미 넣은 눈금과 너무 가까우면 버린다.
 */
const TENOR_MONTHS = [3, 6, 12, 24, 36, 60, 84, 120, 180, 240, 360, 600] as const;

function tenorTicks(
  maxYears: number,
  plotW: number,
  xOf: (y: number) => number,
): { y: number; label: string }[] {
  const cand = TENOR_MONTHS.filter((m) => m / 12 <= maxYears + 1e-9)
    .map((m) => ({ y: m / 12, m, w: weightOf(m) }))
    .sort((a, b) => b.w - a.w || a.y - b.y);
  /* 라벨 최장 `50Y` 가 ~22px 이다(11px 글꼴) — 여유를 둬 34px 보다 가까우면 버린다. */
  const MIN_GAP = Math.min(34, plotW / 4);
  const kept: { y: number; label: string }[] = [{ y: 0, label: '0' }];
  for (const c of cand) {
    if (kept.every((k) => Math.abs(xOf(c.y) - xOf(k.y)) >= MIN_GAP)) {
      /* ★축의 눈금은 **만기 이름**이지 «어떤 종목의 잔존» 이 아니다.
         09-23 의 「1년 안쪽은 일」은 행의 잔존 칸 규칙이다 — 거기서는 하루가 곧
         값이라 `243일` 이 옳다. 축에서 `91일` 은 «3개월» 을 어렵게 적은 것이고,
         딜러는 그 자리를 `3M` 이라 부른다(v2 `chart/tenor.monthsLabel` 과 같은 어휘). */
      kept.push({ y: c.y, label: monthsLabel(c.m) });
    }
  }
  return kept.sort((a, b) => a.y - b.y);
}

/** ★눈금은 데이터가 아니라 «격자» 에서 나온다 — 1·2·2.5·5 ×10^k 중 하나를 고른다.
 *  차트가 읽히느냐 마느냐가 대부분 여기서 갈린다. y 축이 이것을 쓴다. */
function niceTicks(lo: number, hi: number, want = 5): number[] {
  if (!(hi > lo)) return [lo];
  const raw = (hi - lo) / want;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag;
  const out: number[] = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi + step * 1e-9; t += step) {
    out.push(Math.round(t / step) * step);
  }
  return out;
}

type Pt = { ttm?: number; ytm?: number; bpe?: number; n?: string };

export function Curve({ curve, grade, range }: {
  curve: NonNullable<View['curve']>;
  grade?: View['grade_curve'];
  /** x축 상한(년). 0 이면 전체. 옛 화면 `crvRange` 와 같은 뜻이고 기본도 같은 10년이다.
   *  ★없으면 국고 50년물 하나가 축을 48년까지 늘려 나머지 점이 왼쪽에 뭉갠다. */
  range: number;
}) {
  /* ★실제 픽셀로 그린다 [2026-09-28] — 종전에는 560×260 `viewBox` 를 CSS 로 늘려
     그렸고, 그러면 11px 글꼴과 61px 축 폭이 카드 폭에 따라 같이 늘어난다. 축
     글자가 카드마다 다른 크기가 되면 그건 «같은 문법» 이 아니다. */
  const [wrapRef, wrapW, wrapH] = useMeasure<HTMLDivElement>();
  const W = Math.max(320, wrapW || 560);
  /* 그림 높이는 **카드가 준다** [2026-09-29 「한 화면」]. 종전에는 상수였고, 그러면
   * 카드가 커져도 그림은 그대로이고 카드가 작아지면 그림이 카드를 밀어냈다.
   * 이제 `.sr-plot` 이 남는 높이를 먹고(`kbond.css` 의 `.kb-plotwrap`), 그림은 그
   * 칸을 재서 그린다. 상수는 **첫 프레임의 기본값**으로만 남는다 — 재기 전 한 번은
   * 0 이고, 0 으로 그리면 라이브러리가 캔버스를 안 만든다. */
  const H = Math.max(72, wrapH || 240);
  /* 오른쪽 축 폭은 시세·맥박(캔버스)과 **같은 수**를 쓴다 — 두 그림이 한 화면에
     서면 플롯의 오른쪽 끝이 어긋나 보인다. */
  const pad = { l: 8, r: CROSSHAIR_LABEL_MIN_W, t: 12, b: 24 };
  const svgRef = useRef<SVGSVGElement>(null);
  const [hot, setHot] = useState<number | null>(null);

  const line = useMemo(
    () => ((curve.mp_line ?? []) as number[][]).filter((p) => !range || (p[0] ?? 0) <= range),
    [curve, range],
  );
  const pts = useMemo(
    () => ((curve.offers ?? []) as Pt[]).filter((p) => !range || (p.ttm ?? 0) <= range),
    [curve, range],
  );

  const box = useMemo(() => {
    const xs: number[] = [];
    const ys: number[] = [];
    for (const p of pts) {
      if (p.ttm != null) xs.push(p.ttm);
      if (p.ytm != null) ys.push(p.ytm);
    }
    for (const p of line) {
      if (p[0] != null) xs.push(p[0]);
      if (p[1] != null) ys.push(p[1]);
    }
    /* ★등급 커브는 축을 «지배하면» 안 된다 — 20년까지 뻗어 있어 범위에 넣으면
       실제 호가 산점도가 좌하단으로 눌린다(실측). 범위는 호가와 민평선으로만
       잡고, 커브는 그 범위 안으로 잘라 그린다. */
    if (!xs.length || !ys.length) return null;
    const x1 = range || Math.max(...xs) || 1;
    let y0 = Math.min(...ys);
    let y1 = Math.max(...ys);
    const m = (y1 - y0) * 0.08 || 0.05;
    y0 -= m;
    y1 += m;
    return { x0: 0, x1, y0, y1 };
  }, [pts, line, range]);

  /* ★x 는 **√만기**다(`chart/tenorScale.monthsToX`, v2 의 커브 축과 같은 함수).
     선형 월수로 그리면 30년물 하나가 축을 끌어당겨 1~3년이 왼쪽에 뭉친다 —
     실제로 호가가 가장 촘촘한 구간이 가장 안 보이게 된다. */
  const px = useCallback(
    (x: number) => {
      if (!box) return 0;
      const span = monthsToX(box.x1 * 12) || 1;
      return pad.l + (monthsToX(Math.max(0, x) * 12) / span) * (W - pad.l - pad.r);
    },
    [box, pad.l, pad.r, W],
  );
  const py = useCallback(
    (y: number) => (box ? H - pad.b - ((y - box.y0) / (box.y1 - box.y0 || 1)) * (H - pad.t - pad.b) : 0),
    [box, pad.b, pad.t, H],
  );

  /** ★조준이 아니라 «근처» 면 된다 — SVG 안 아무 데나 두면 가장 가까운 점을 집는다.
   *  반지름 3px 점을 정확히 맞히게 하는 것은 맞히라는 게 아니라 포기하라는 것이다. */
  const onMove = useCallback(
    (ev: React.PointerEvent<SVGSVGElement>) => {
      const el = svgRef.current;
      if (!el || !box) return;
      const r = el.getBoundingClientRect();
      const mx = ((ev.clientX - r.left) / r.width) * W;
      const my = ((ev.clientY - r.top) / r.height) * H;
      let best = -1;
      let bd = Infinity;
      pts.forEach((p, i) => {
        if (p.ttm == null || p.ytm == null) return;
        const d = (px(p.ttm) - mx) ** 2 + (py(p.ytm) - my) ** 2;
        if (d < bd) {
          bd = d;
          best = i;
        }
      });
      setHot(bd <= 60 * 60 && best >= 0 ? best : null);
    },
    [box, pts, px, py, W, H],
  );

  const onKey = useCallback(
    (ev: React.KeyboardEvent<SVGSVGElement>) => {
      if (!pts.length) return;
      if (ev.key === 'ArrowRight' || ev.key === 'ArrowLeft') {
        ev.preventDefault();
        const d = ev.key === 'ArrowRight' ? 1 : -1;
        setHot((h) => (h == null ? 0 : (h + d + pts.length) % pts.length));
      } else if (ev.key === 'Escape') {
        setHot(null);
      }
    },
    [pts.length],
  );

  if (!box) return <div className="kb-empty">그릴 점이 없습니다</div>;

  const path = line
    .filter((p) => p[0] != null && p[1] != null)
    .map((p, i) => `${i ? 'L' : 'M'}${px(p[0]).toFixed(1)},${py(p[1]).toFixed(1)}`)
    .join(' ');
  const gradePath = (grade?.pts ?? [])
    .filter((p) => p.ttm <= box.x1 && p.y >= box.y0 && p.y <= box.y1)
    .map((p, i) => `${i ? 'L' : 'M'}${px(p.ttm).toFixed(1)},${py(p.y).toFixed(1)}`)
    .join(' ');

  /* ★y 눈금 수는 **높이에서 나온다** — v2 캐논의 `tickMarkDensity: 4` 와 같은 뜻
     (한 칸 = 글자크기 × 4). 손으로 고른 7 은 판이 좁아지면 촘촘해지고 넓어지면
     성겨진다. 여기서는 판이 말하게 둔다. */
  const plotH = H - pad.t - pad.b;
  const yTicks = niceTicks(box.y0, box.y1, Math.max(3, Math.round(plotH / (AXIS_FONT_PX * TICK_DENSITY))));
  const xTicks = tenorTicks(box.x1, W - pad.l - pad.r, px);
  const p = hot != null ? pts[hot] : null;
  const hx = p?.ttm != null ? px(p.ttm) : 0;
  const hy = p?.ytm != null ? py(p.ytm) : 0;

  /* ── 리드아웃 한 줄 ────────────────────────────────────────────────────── */
  const idle = pts.reduce<number | null>(
    (best, q, i) => (q.ttm == null ? best : best == null || (q.ttm ?? 0) > (pts[best].ttm ?? 0) ? i : best),
    null,
  );
  const readAt = hot ?? idle;
  const r = readAt == null ? null : pts[readAt];
  const slots: StripSlot[] = [
    {
      key: 'ytm',
      label: 'YTM',
      value: fmtYield(r?.ytm),
      color: r?.bpe == null ? 'var(--color-fgMuted)' : r.bpe < 0 ? 'var(--sr-down)' : 'var(--sr-up)',
      chars: slotChars(fmtYield, box.y0, box.y1),
    },
    { key: 'ttm', label: '잔존', value: fmtTtm(r?.ttm), chars: 5, drop: 1 },
    { key: 'mp', label: '민평선', value: '', color: 'var(--color-fgMuted)', opacity: 0.9 },
  ];
  if (gradePath) {
    slots.push({ key: 'gr', label: '등급커브', value: '', color: 'var(--color-fgMuted)', opacity: 0.9 });
  }

  return (
    <div className="kb-plotwrap">
      {/* ★범례를 흡수한 한 줄 — 견본(그려진 색)·이름·값이 한 자리에 있다
          [v2 §8.5b]. 커서가 그림 밖이면 «가장 긴 잔존» 을 읽는다: 빈 상태가
          없으므로 줄이 생겼다 사라지며 그림 높이를 흔드는 일이 없다. */}
      <ChartReadoutStrip
        date={r?.n ?? ''}
        slots={slots}
        change={r?.bpe == null ? undefined : { label: '민평 대비', text: fmtBpUnit(r.bpe), v: r.bpe }}
      />
      <div className="sr-plot" ref={wrapRef}>
        <svg
          ref={svgRef}
          className="kb-curve"
          width={W}
          height={H}
          viewBox={`0 0 ${W} ${H}`}
          role="application"
          tabIndex={0}
          aria-label={`잔존 대 YTM 산점도. 점 ${pts.length}개. 화살표 키로 점을 옮깁니다.`}
          onPointerMove={onMove}
          onPointerLeave={() => setHot(null)}
          onKeyDown={onKey}
        >
          {/* ★격자가 없다 — 눈금이 곧 자다(v2 `canonOptions.grid`). */}
          {yTicks.map((y) => (
            <text key={`y${y}`} x={W - pad.r + 6} y={py(y) + 3} className="kb-ax">
              {fmtAxis(y)}
            </text>
          ))}
          {xTicks.map((x) => (
            <text key={`x${x.y}`} x={px(x.y)} y={H - 7} className="kb-ax" textAnchor="middle">
              {x.label}
            </text>
          ))}
          {path ? <path d={path} className="kb-mpline" /> : null}
          {gradePath ? <path d={gradePath} className="kb-gradeline" /> : null}
          {pts.map((q, i) =>
            q.ttm == null || q.ytm == null ? null : (
              <circle
                key={i}
                cx={px(q.ttm)}
                cy={py(q.ytm)}
                r={i === hot ? 5 : 3}
                className={`kb-pt ${q.bpe == null ? '' : q.bpe < 0 ? 'dn' : 'up'}${
                  i === hot ? ' on' : ''
                }`}
              />
            ),
          )}
          {/* ★십자선은 **세로만** 긋고 자리는 축 칩이 말한다 — 캔버스 차트의
              `crosshair.horzLine.visible: false, labelVisible: true` 와 같은 그림이다.
              가로로 그림을 가로지르는 선은 «그림 위에 덧대는 것» 이고, 이번에
              말풍선을 걷은 것과 같은 계열이다. */}
          {p ? (
            <g>
              <line className="kb-xh" x1={hx} x2={hx} y1={pad.t} y2={H - pad.b} />
              <g className="kb-xl">
                <rect x={W - pad.r + 2} y={hy - 8} width={pad.r - 4} height={16} rx={2} />
                <text x={W - pad.r + 6} y={hy + 3}>{fmtAxis(p.ytm ?? 0)}</text>
              </g>
              <g className="kb-xl">
                <rect x={Math.max(0, hx - 20)} y={H - pad.b + 1} width={40} height={15} rx={2} />
                <text x={Math.max(20, hx)} y={H - pad.b + 12} textAnchor="middle">
                  {fmtTtm(p.ttm)}
                </text>
              </g>
            </g>
          ) : null}
        </svg>
      </div>
    </div>
  );
}
