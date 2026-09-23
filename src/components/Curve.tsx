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
 * 규율(dataviz)
 *  · 점은 작게, 격자·축은 실선 헤어라인으로 «뒤로» 물린다(점선 금지 — 점선 격자는
 *    «추정치» 로 읽힌다).
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

const n3 = (v?: number | null) => (v == null ? '—' : v.toFixed(3));
const sbp = (v?: number | null) => (v == null ? '' : `${v > 0 ? '+' : ''}${v.toFixed(1)}`);
const ttmTxt = (t?: number | null) =>
  t == null ? '' : t < 1 ? `${Math.round(t * 12)}M` : `${t.toFixed(1)}년`;
/** 축 눈금용 — ★«2.0년» 이 아니라 «2년». 눈금에 뜻 없는 소수는 잡음이고,
 *  자에 8.8 이 적혀 있으면 자가 아니듯 2.0 도 읽는 눈을 한 번 더 세운다. */
const tickTxt = (t: number) =>
  t === 0 ? '0' : t < 1 ? `${Math.round(t * 12)}M` : `${Number.isInteger(t) ? t : t.toFixed(1)}년`;

/** ★눈금은 데이터가 아니라 «격자» 에서 나온다 — 1·2·2.5·5 ×10^k 중 하나를 고른다.
 *  차트가 읽히느냐 마느냐가 대부분 여기서 갈린다. */
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
  const W = 560;
  const H = 260;
  const pad = { l: 46, r: 12, t: 12, b: 26 };
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

  const px = useCallback(
    (x: number) => (box ? pad.l + ((x - box.x0) / (box.x1 - box.x0 || 1)) * (W - pad.l - pad.r) : 0),
    [box, pad.l, pad.r],
  );
  const py = useCallback(
    (y: number) => (box ? H - pad.b - ((y - box.y0) / (box.y1 - box.y0 || 1)) * (H - pad.t - pad.b) : 0),
    [box, pad.b, pad.t],
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
    [box, pts, px, py],
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

  /* ★y 는 한 단 촘촘히(7) — 크레딧은 등급이 섞여 폭이 3%p 를 넘는데, 눈금이
     셋(3·4·5)뿐이면 «둥글지만 못 읽는» 자가 된다. 7 이면 이 폭에서 0.5 단위가,
     국고처럼 좁은 판에선 0.1 단위가 잡힌다. 격자는 그만큼 옅게 둔다. */
  const yTicks = niceTicks(box.y0, box.y1, 7);
  const xTicks = niceTicks(box.x0, box.x1, 5);
  const p = hot != null ? pts[hot] : null;
  const hx = p?.ttm != null ? px(p.ttm) : 0;
  const hy = p?.ytm != null ? py(p.ytm) : 0;

  return (
    <div className="kb-curvewrap">
      {/* ★범례는 «2계열 이상이면 늘» 선다 — 색만으로 말하지 않기 위해서다.
          점의 색은 민평 대비 부호이고, 그 뜻이 글자로도 같이 적힌다. */}
      <div className="kb-legend">
        <span><i className="sw line mp" />민평선</span>
        {gradePath ? <span><i className="sw line gr" />등급커브</span> : null}
        <span><i className="sw dot up" />민평 위</span>
        <span><i className="sw dot dn" />민평 아래</span>
      </div>
      <svg
        ref={svgRef}
        className="kb-curve"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        tabIndex={0}
        aria-label={`잔존 대 YTM 산점도. 점 ${pts.length}개. 화살표 키로 점을 옮깁니다.`}
        onPointerMove={onMove}
        onPointerLeave={() => setHot(null)}
        onKeyDown={onKey}
      >
        {yTicks.map((y) => (
          <g key={`y${y}`}>
            <line x1={pad.l} x2={W - pad.r} y1={py(y)} y2={py(y)} className="kb-grid" />
            <text x={pad.l - 7} y={py(y) + 3} className="kb-axis" textAnchor="end">
              {y.toFixed(2)}
            </text>
          </g>
        ))}
        {xTicks.map((x) => (
          <g key={`x${x}`}>
            <line x1={px(x)} x2={px(x)} y1={pad.t} y2={H - pad.b} className="kb-grid v" />
            <text x={px(x)} y={H - 8} className="kb-axis" textAnchor="middle">
              {tickTxt(x)}
            </text>
          </g>
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
        {/* 십자선 — 집힌 점의 자리를 축까지 이어 준다. 어느 잔존·어느 금리인지
            말풍선을 안 읽어도 축에서 바로 보인다. */}
        {p ? (
          <g className="kb-xhair">
            <line x1={hx} x2={hx} y1={pad.t} y2={H - pad.b} />
            <line x1={pad.l} x2={W - pad.r} y1={hy} y2={hy} />
          </g>
        ) : null}
      </svg>
      {/* ★값이 앞, 이름이 뒤 — 읽는 사람은 종목을 이미 알고 «수» 를 원한다. */}
      {p ? (
        <div
          className="kb-tip"
          style={{
            left: `${(hx / W) * 100}%`,
            top: `${(hy / H) * 100}%`,
            transform: hx > W * 0.6 ? 'translate(-108%, -50%)' : 'translate(8%, -50%)',
          }}
        >
          <b>{n3(p.ytm)}</b>
          <span className={p.bpe == null ? '' : p.bpe < 0 ? 'dn' : 'up'}>
            {p.bpe == null ? '' : `민평 ${sbp(p.bpe)}bp`}
          </span>
          <em>{p.n ?? ''}</em>
          <span className="ttm">잔존 {ttmTxt(p.ttm)}</span>
        </div>
      ) : null}
    </div>
  );
}
