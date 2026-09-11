'use client';

/**
 * 전일 민평 대비 히트맵 — 종별×등급 행 × 잔존 버킷 열.
 *
 * ★칸 값(중앙 민평대비·건수·추정 수)은 `kbond_view.heat_cells` 가 낸다. 여기서는
 *   그리기만 한다.
 *
 * ★모양은 옛 화면(`kbond_live.html` 의 `.hm`)을 그대로 따랐다 [OWNER 2026-09-04
 *   「원래 ibond 랑 유사하게」] — 표 괘선이 아니라 **칸마다 둥근 상자**이고
 *   (border-spacing 3px · radius 8 · height 34 · weight 700), 건수는 값 뒤에
 *   작게 붙는다. 트레이더가 이미 그 배치로 읽고 있다.
 *
 * ★[2026-09-11] 옛 화면에 있던 둘을 마저 옮겼다.
 *   1) **묵은 민평 표시**. 서버가 `stale` 을 실어 보내는데 여기서 버리고 있었다 —
 *      통안 최신물은 민평 적재가 며칠 늦어 그 «대비» 가 전일 대비가 아닌데,
 *      경고 없이 그리면 16일 전 민평과의 차이가 오늘 움직임처럼 읽힌다(실측
 *      2026-09-11 통안 2029-03-03: 민평 기준일 08-26 · 칸 값 +18.0bp).
 *   2) **등급 무시 토글**. 등급을 합친 칸은 서버가 «종별|*|버킷» 으로 따로 쌓아
 *      준다 — 중앙값끼리는 못 합치기 때문이다(등급별 중앙을 다시 중앙 내면 딴
 *      수가 된다).
 */
import { useState } from 'react';

import type { View } from '@/lib/api';

const sbp = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)}`;

type Cell = { med?: number | null; n?: number; est?: number };

export function Heat({ heat, title }: { heat: NonNullable<View['heat']>; title?: string }) {
  const [all, setAll] = useState(false);
  const cells = (heat.cells ?? {}) as Record<string, Cell>;
  const rows = (heat.rows ?? []) as (string | null)[][];
  const buckets = (heat.buckets ?? []) as string[];
  const stale = !!heat.stale;
  /* 등급을 무시해도 «칸이 있나» 는 같은 자리에서 봐야 한다 — 키만 갈아 끼운다. */
  const keyOf = (cls: string, rt: string | null, b: string) =>
    `${cls}|${rt == null ? '미상' : all ? '*' : rt}|${b}`;
  /* 진하기의 분모는 «지금 그리는 칸» 에서만 잡는다 — 등급 지정일 때 합친 칸(|*|)이
     섞이면 색이 통째로 옅어진다. */
  const shownKey = (k: string) =>
    all ? k.includes('|*|') || k.includes('|미상|') : !k.includes('|*|');
  const vals = Object.entries(cells)
    .filter(([k]) => shownKey(k))
    .map(([, c]) => c.med)
    .filter((v): v is number => v != null);
  if (!vals.length) return <div className="kb-empty">살아 있는 칸이 없습니다</div>;
  const mx = Math.max(1, ...vals.map((v) => Math.abs(v)));

  return (
    <div className="kb-hmwrap">
      <div className="kb-hmttl">
        {title ? <span>{title}</span> : null}
        <button
          className={`kb-pill${all ? ' on' : ''}`}
          onClick={() => setAll((v) => !v)}
          title="등급을 합쳐서 봅니다 — 칸은 서버가 원자료에서 다시 접은 값입니다"
        >
          {all ? '등급 무시' : '등급 지정'}
        </button>
      </div>
      <table className="kb-hm">
        <thead>
          <tr>
            <th className="l">종별</th>
            {buckets.map((b) => (
              <th key={b}>{b}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(([cls, rt]) => {
            /* 통안 최신물만 민평이 늦는다 — 별표는 그 행에만 붙인다(옛 화면과 같다). */
            const rowStale = stale && cls === '통안채';
            return (
              <tr key={`${cls}|${rt}`}>
                <td
                  className="l"
                  title={
                    rowStale
                      ? '통안 최신물은 민평 적재가 며칠 늦다 — 전일 대비가 아니다'
                      : undefined
                  }
                >
                  {cls}
                  {rowStale ? ' *' : ''}
                  {rt ? <span className="g">{all ? '전체' : rt}</span> : null}
                </td>
                {buckets.map((b) => {
                  const c = cells[keyOf(cls as string, rt, b)];
                  if (!c || c.med == null) {
                    return (
                      <td key={b} className="e">
                        ·
                      </td>
                    );
                  }
                  /* 진하기는 |값|/최댓값. 0.18 을 바닥으로 둬 «값이 있다» 가 보이게 한다. */
                  const w = Math.max(0.18, Math.min(1, Math.abs(c.med) / mx));
                  const col = c.med < 0 ? 'var(--sr-down)' : 'var(--sr-up)';
                  return (
                    <td
                      key={b}
                      style={{
                        background: `color-mix(in srgb, ${col} ${(w * 26).toFixed(0)}%, var(--sr-page))`,
                        color: `color-mix(in srgb, ${col} 88%, var(--color-fg))`,
                      }}
                      title={`${cls} ${rt == null ? '' : all ? '전체' : rt} · 잔존 ${b} · ${c.n}건${c.est ? ` · 추정 ${c.est}` : ''}${rowStale ? ' · 민평이 그날 것이 아님' : ''}`}
                    >
                      {sbp(c.med)}
                      {c.n ? <span className="c">{c.n}</span> : null}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="kb-hmleg">
        <i className="dn" /> 강세(−)
        <i className="up" /> 약세(+)
        <span className="kb-n">칸 = 중앙값 bp · 작은 수 = 호가 건수</span>
      </div>
      <div className="kb-hmnote">
        국고·통안은 (현재 mid − 전일 민평) · 크레딧은 문면에 적힌 민평 대비 bp, 매도 호가만입니다
        {stale ? ' · * 통안은 민평이 그날 것이 아님' : ''}
      </div>
    </div>
  );
}
