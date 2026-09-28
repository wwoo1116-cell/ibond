'use client';

/**
 * 동향 화면 — 시장 맥박 / 이벤트 / 커브 오늘 / 딜러 리더보드.
 *
 * ★계산 없음. 칸별 건수·어제 대비·이벤트 집계·지표물 Δbp·리더보드 정렬은
 *   `kbond_view.py` 의 `pulse_stats`·`event_counts`·`curve_today`·`leaderboard` 가 낸다.
 *   여기서는 칸 값을 막대 높이로 옮길 뿐이다.
 */
import { Fragment, useCallback, useEffect, useState } from 'react';

import dynamic from 'next/dynamic';
import type React from 'react';

import { Text } from '@coinbase/cds-web/typography';

import { getView } from '@/lib/api';
import type { TtlMode, View } from '@/lib/api';
import {
  EMDASH, fmtBpLevel, fmtCount, fmtHm, fmtHms, fmtLotBlank, fmtMin, fmtPct, fmtRatio, fmtSigned,
  fmtYield,
} from '@/lib/format';
import { Delta } from '@/ui/Delta';
import { ColGroup } from '@/ui/ColGroup';
import { TABLES } from '@/lib/columns';

type Ev = NonNullable<View['events']>[number];
type Leader = NonNullable<View['leaderboard']>;


/* 맥박 차트는 `components/PulseChart.tsx` 로 나갔다 [2026-09-28] — 손 SVG 를 걷고
   v2 차트 캐논으로 다시 그렸다. 범주색도 그때 방향쌍(매도 파랑·매수 빨강)에서
   참조색으로 옮겼다: 이 앱에서 빨강·파랑은 이미 두 뜻을 지고 있다. */
const PulseChart = dynamic(() => import('./PulseChart').then((m) => m.PulseChart), {
  ssr: false,
  loading: () => <div className="kb-empty">맥박을 그리는 중…</div>,
});

const LANE_LBL: Record<string, string> = { ktb: '국고', msb: '통안', nhb: '국민주택', cr: '크레딧' };

const EVK: Record<string, string> = {
  first: '첫호가',
  best: '최우선',
  cross: '크로스',
  size: '대량',
  fill: '체결',
};

/** 이벤트 한 줄의 말. 옛 화면 evText 와 같은 문면이다. */
function evText(e: Ev) {
  const x = (e.x ?? {}) as { prev?: number; vs?: number; vd?: string; csrc?: string };
  const nm = e.n ?? e.code ?? '';
  const y = e.y != null ? fmtYield(e.y) : '';
  const a = fmtLotBlank(e.a);
  if (e.k === 'best') return `${nm} 최우선 ${y} (이전 ${fmtYield(x.prev)})`;
  if (e.k === 'cross') {
    const gap = x.vs != null && e.y != null ? Math.abs(e.y - x.vs) * 100 : null;
    return `${nm} ${y} 가 ${x.vd ?? ''} 의 ${fmtYield(x.vs)} 을 ${gap != null ? `${fmtBpLevel(gap)}bp ` : ''}뚫음${a ? ` · ${a}` : ''}`;
  }
  if (e.k === 'fill') return `${nm} ${y} ${a}`;
  if (e.k === 'size') return `${nm} ${y} ${a}`;
  if (e.k === 'first') return `${nm} 오늘 첫 호가 ${y}`;
  return nm;
}

function Leaderboard({ lb, lane, onLane }: {
  lb: Leader;
  lane: string;
  onLane: (l: string) => void;
}) {
  const rows = lb.rows ?? [];
  const maxN = Math.max(1, ...rows.map((r) => r.ln ?? 0));
  /* 딜러를 누르면 그 줄 아래가 펼쳐진다 — 옛 화면의 `dlSel` 자리다.
     쓰는 값은 이미 리더보드에 실려 온 것뿐이라 서버를 더 부르지 않는다. */
  const [sel, setSel] = useState<string | null>(null);
  return (
    <>
      <div className="kb-pills">
        {[['all', '전체'], ['ktb', '국고'], ['msb', '통안'], ['cr', '크레딧']].map(([k, n]) => (
          <button key={k} className={`kb-pill${lane === k ? ' on' : ''}`} onClick={() => onLane(k)}>
            {n}
          </button>
        ))}
      </div>
      <table className="kb-tbl">
        <ColGroup cols={TABLES.leaderboard} />
        <thead>
          <tr>
            <th className="l">딜러</th>
            <th>건수</th>
            <th title="호가 중 매도/매수">매도/매수</th>
            <th title="그 딜러가 보낸 체결 응답 수">체결</th>
            <th title="맞은 호가의 주인으로 센 체결 — 딜러+레벨 귀속이면 그 딜러, 레벨만이면 그 레벨의 남">귀속</th>
            <th title="오늘 최우선에 서 있던 시간 합">최우선</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 60).map((d, i) => {
            const q = (d.s ?? 0) + (d.b ?? 0);
            const pb = q ? Math.round((100 * (d.b ?? 0)) / q) : 0;
            const open = sel === `${d.k}${i}`;
            return (
              <Fragment key={`${d.k}${i}`}>
              <tr
                className={`dl${open ? ' on' : ''}`}
                title={`${d.d ?? ''} · 첫 ${fmtHms(d.first ?? 0)} 마지막 ${fmtHms(d.last ?? 0)}`}
                onClick={() => setSel(open ? null : `${d.k}${i}`)}
              >
                <td className="l">{d.d}</td>
                <td className="num">{d.ln}</td>
                <td>
                  <span className="kb-sb" style={{ width: `${Math.max(6, Math.round((56 * q) / maxN))}px` }}>
                    <i style={{ width: `${pb}%` }} />
                  </span>
                </td>
                <td className="num kb-n">{d.c || ''}</td>
                <td className="num">{d.f || ''}</td>
                <td className="num kb-n">{d.ab ? fmtMin(d.ab) : ''}</td>
              </tr>
              {open ? (
                <tr className="dld">
                  <td colSpan={6}>
                    <div className="kb-dld">
                      <span className="kb-n">
                        첫 {fmtHms(d.first ?? 0)} · 마지막 {fmtHms(d.last ?? 0)}
                        {d.lane
                          ? ` · ${Object.entries(d.lane)
                              .sort((x, y) => y[1] - x[1])
                              .slice(0, 3)
                              .map(([k, v]) => `${LANE_LBL[k] ?? k} ${v}`)
                              .join(' · ')}`
                          : ''}
                      </span>
                      <div className="codes">
                        {(d.codes ?? []).slice(0, 12).map((x, j) => (
                          <span key={j} className="kb-badge">
                            {String((x as unknown[])[0]).slice(0, 12)}
                            <b>{String((x as unknown[])[1])}</b>
                          </span>
                        ))}
                        {!(d.codes ?? []).length ? <span className="kb-n">종목 기록 없음</span> : null}
                      </div>
                    </div>
                  </td>
                </tr>
              ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </>
  );
}

export function Trends({ ttl, onTtl }: { ttl: TtlMode; onTtl?: (t: TtlMode) => void }) {
  const [v, setV] = useState<View | null>(null);
  const [dlLane, setDlLane] = useState('all');
  const [evOn, setEvOn] = useState<Record<string, boolean>>({
    first: true, best: true, cross: true, size: true, fill: true,
  });
  const [err, setErr] = useState<string | null>(null);

  const pull = useCallback(async () => {
    try {
      setV(await getView('dyn', ttl, dlLane === 'all' ? undefined : dlLane));
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : '실패');
    }
  }, [ttl, dlLane]);

  useEffect(() => {
    void pull();
    const id = setInterval(() => void pull(), 5000);
    return () => clearInterval(id);
  }, [pull]);

  if (err) return <div className="kb-empty">백엔드에 못 붙었습니다 — {err}</div>;
  if (!v?.pulse) return <div className="kb-empty">부르는 중…</div>;

  const p = v.pulse;
  const bi = v.book_info;
  const cnt = v.event_counts ?? {};
  const evs = (v.events ?? []).filter((e) => evOn[e.k ?? '']).slice().reverse();
  const ct = v.curve_today ?? {};
  const LANE_NM: Record<string, string> = { ktb: '국고', msb: '통안' };

  /* 값은 글자일 수도, 원소일 수도 있다 — 변화는 «네 부품 한 벌»(`ui/Delta`)이라
     글자로 못 담는다. 색은 그 부품이 스스로 지므로 `cls` 는 레벨용으로만 남는다. */
  const kv = (label: string, value: React.ReactNode, cls = '') => (
    <div className="kb-kvc" key={label}>
      <span className="kb-n">{label}</span>
      <b className={cls}>{value}</b>
    </div>
  );

  return (
    <div className="kb-trends">
      <div className="kb-mid">
        <div className="kb-card">
          <div className="kb-ch">
            <Text as="span" font="label2">시장 맥박</Text>
            <Text as="span" font="legal" color="fgMuted" className="kb-ch-meta">
              {p.bin / 60}분 단위
              {p.t0 != null ? ` · ${fmtHm(p.t0)}~${fmtHm(p.t1 ?? p.t0)}` : ''}
            </Text>
            {onTtl ? (
              <select
                className="kb-sel"
                value={ttl}
                onChange={(ev) => onTtl(ev.target.value as TtlMode)}
                title="호가 수명 — 화면 필터일 뿐 책을 바꾸지 않는다"
              >
                <option value="def">활성</option>
                <option value="half">타이트</option>
                <option value="inf">세션</option>
              </select>
            ) : null}
          </div>
          <div className="kb-kvgrid">
            {kv('호가 · 관심', `${fmtCount(p.nq)} · ${fmtCount(p.na)}`)}
            {/* v12 체결 귀속의 부산물 — 오퍼가 맞았으면 사 간 것, 비드면 판 것.
                장외 대화록에 없던 축이다. 서버가 세고 화면은 읽기만 한다.
                ★합계가 체결 응답 수보다 작다: 내용 없는 «ㅎㅈ» 은 책에 못 붙는다. */}
            {kv(
              '체결 응답 — 사 감 · 팜',
              `${fmtCount(p.nc)} ${EMDASH} ${v.aggr?.B ?? 0} · ${v.aggr?.S ?? 0}`,
            )}
            {kv('호가/체결', p.nc ? fmtRatio(p.nq / p.nc, 1) : EMDASH)}
            {kv('어제 같은 시각 대비', <Delta v={p.vs_prev_pct} unit="%" />)}
            {kv('국고 · 통안 · 크레딧', `${p.ktb} · ${p.msb} · ${p.cr}`)}
            {kv('문의', fmtCount(p.ni))}
            {kv(
              '딜러(데스크)',
              `${p.n_dealer}${p.prev_n_dealer ? ` / 어제 ${p.prev_n_dealer}` : ''}`,
            )}
            {kv('이벤트', fmtCount(p.n_event))}
          </div>
          {/* +++ 책이 말하는 것 — 귀속 체결(국고·통안)에서 엔진이 «체결 순간» 에 재 둔 값.
              국고 전 이력 실측(RESULT_book_dynamics_2026-09-15.md):
                · 책은 한 틱(0.5bp, 93.6%)이고 체결의 81% 가 최우선 레벨에서 난다 → 유효 = 호가 반스프레드
                · 직전 불균형(잠금 동점 제외): 비드 우세 → 사 감 59.5% · 오퍼 우세 → 39.1% (위약 AUC 0.51 대 0.58)
              여기 수는 «오늘» 이 그 실측과 같은 자리에 있는지 보는 것이다. 표본이 작은 날은 흔들린다. */}
          {bi ? (
            <div className="kb-kvgrid" style={{ marginTop: 6 }}>
              {kv(
                '유효 반스프레드 · 호가 (bp)',
                bi.eff_med == null
                  ? '—'
                  : `${fmtBpLevel(bi.eff_med, 2)} · ${fmtBpLevel(bi.qs_half_med, 2)}`,
              )}
              {kv(
                '최우선 레벨에서 난 체결',
                bi.at_best_pct == null ? EMDASH : `${fmtPct(bi.at_best_pct)} / ${bi.n_ab}건`,
              )}
              {kv(
                '직전 불균형 → 사 감 % (오퍼·균형·비드)',
                bi.n_imb
                  ? ['오퍼 우세', '균형', '비드 우세']
                      .map((k) => {
                        const c = bi.p_b_by_imb?.[k];
                        return c && c.pB != null ? `${fmtPct(c.pB)}(${c.n})` : EMDASH;
                      })
                      .join(' · ')
                  : '—',
              )}
              {kv(
                '귀속 체결 · 불균형 잰 것',
                `${bi.n} · ${bi.n_imb}${bi.n_imb_prev ? ` (+${bi.n_imb_prev})` : ''}`,
              )}
            </div>
          ) : null}
          <PulseChart p={p} />
        </div>

        <div className="kb-card">
          <div className="kb-ch">
            <Text as="span" font="label2">이벤트</Text>
            <Text as="span" font="legal" color="fgMuted" className="kb-ch-meta">
              최근 {(v.events ?? []).length}건 중 {evs.length}
            </Text>
          </div>
          <div className="kb-pills">
            {Object.keys(EVK).map((k) => (
              <button
                key={k}
                className={`kb-pill${evOn[k] ? ' on' : ''}`}
                onClick={() => setEvOn((s) => ({ ...s, [k]: !s[k] }))}
              >
                {EVK[k]} <span className="kb-n">{cnt[k] ?? 0}</span>
              </button>
            ))}
          </div>
          <div className="kb-scroll">
            {evs.slice(0, 300).map((e, i) => (
              /* 이벤트 문장은 길이가 자료라 어떤 폭도 모자랄 수 있다 —
                 잘리면 «…» 로 보이고 전체는 이 `title` 이 준다. */
              <div className="kb-ev" key={i} title={evText(e)}>
                <span className="kb-n">{fmtHms(e.t ?? 0)}</span>
                <span className={`kb-evk ${e.k}`}>{EVK[e.k ?? ''] ?? e.k}</span>
                <span className={e.s === 'S' ? 'kb-side-s' : e.s === 'B' ? 'kb-side-b' : undefined}>
                  {e.s === 'S' ? '매도' : e.s === 'B' ? '매수' : ''}
                </span>
                <span className="kb-evt">{evText(e)}</span>
                <span className="kb-n">{e.d}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="kb-right">
        <div className="kb-card">
          <div className="kb-ch">
            <Text as="span" font="label2">커브 오늘</Text>
            <Text as="span" font="legal" color="fgMuted" className="kb-ch-meta">지표 · 차기지표</Text>
          </div>
          <table className="kb-tbl">
            {/* ★인라인 px 를 걷었다 [2026-09-28] — 폭은 `lib/columns` 한 곳이 정한다.
                다섯 표 중 하나만 자기 폭을 들고 있으면 그 표만 다른 규칙으로 산다. */}
            <ColGroup cols={TABLES.curveToday} />
            <thead>
              <tr>
                <th className="l">연물</th>
                <th className="l">종목</th>
                <th>전일민평</th>
                <th>mid</th>
                <th>Δbp</th>
                <th title="살아 있는 오퍼 딜러 · 비드 딜러 (▲ 비드 우세 · ▼ 오퍼 우세)">딜러</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(ct).map(([lane, rows]) =>
                !rows.length ? null : (
                  <Fragment key={lane}>
                    <tr>
                      <td colSpan={6} className="l kb-n" style={{ paddingTop: 8 }}>
                        {LANE_NM[lane] ?? lane}
                      </td>
                    </tr>
                    {rows.map((r) => (
                      <tr key={`${lane}${r.c}`} title={r.full ?? r.nm ?? r.c}>
                        <td className="l kb-n">{r.ten}</td>
                        <td className="l">
                          {lane === 'msb' ? (r.alias ?? r.c) : r.c}
                          {r.bench ? <b className="kb-badge">지표</b> : null}
                          {r.next ? <b className="kb-badge">차기</b> : null}
                        </td>
                        <td className="num kb-n">{fmtYield(r.mp)}</td>
                        <td className="num">{fmtYield(r.mid)}</td>
                        <td className="num">
                          <Delta v={r.dbp} />
                        </td>
                        <td
                          className="num kb-n"
                          title={r.imb == null ? '' : `지금 불균형 (비드−오퍼)/합 ${fmtSigned(r.imb, 2)}`}
                        >
                          {r.nd}
                          {r.imb == null ? '' : r.imb > 0.15 ? ' ▲' : r.imb < -0.15 ? ' ▼' : ''}
                        </td>
                      </tr>
                    ))}
                  </Fragment>
                ),
              )}
            </tbody>
          </table>
        </div>

        <div className="kb-card">
          <div className="kb-ch">
            <Text as="span" font="label2">딜러</Text>
            <Text as="span" font="legal" color="fgMuted" className="kb-ch-meta">
              오늘 {v.leaderboard?.n ?? 0}곳 · 건수 순
            </Text>
          </div>
          {v.leaderboard ? (
            <Leaderboard lb={v.leaderboard} lane={dlLane} onLane={setDlLane} />
          ) : null}
        </div>
      </div>
    </div>
  );
}
