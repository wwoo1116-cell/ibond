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
 */
import type { View } from '@/lib/api';

const sbp = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)}`;

type Cell = { med?: number | null; n?: number; est?: number };

export function Heat({ heat, title }: { heat: NonNullable<View['heat']>; title?: string }) {
  const cells = (heat.cells ?? {}) as Record<string, Cell>;
  const rows = (heat.rows ?? []) as (string | null)[][];
  const buckets = (heat.buckets ?? []) as string[];
  const vals = Object.values(cells)
    .map((c) => c.med)
    .filter((v): v is number => v != null);
  if (!vals.length) return <div className="kb-empty">살아 있는 칸이 없습니다</div>;
  const mx = Math.max(1, ...vals.map((v) => Math.abs(v)));

  return (
    <div className="kb-hmwrap">
      {title ? <div className="kb-hmttl">{title}</div> : null}
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
          {rows.map(([cls, rt]) => (
            <tr key={`${cls}|${rt}`}>
              <td className="l">
                {cls}
                {rt ? <span className="g">{rt}</span> : null}
              </td>
              {buckets.map((b) => {
                const c = cells[`${cls}|${rt ?? '미상'}|${b}`];
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
                    title={`${cls} ${rt ?? ''} · 잔존 ${b} · ${c.n}건${c.est ? ` · 추정 ${c.est}` : ''}`}
                  >
                    {sbp(c.med)}
                    {c.n ? <span className="c">{c.n}</span> : null}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="kb-hmleg">
        <i className="dn" /> 강세(−)
        <i className="up" /> 약세(+)
        <span className="kb-n">칸 = 중앙값 bp · 작은 수 = 호가 건수</span>
      </div>
    </div>
  );
}
