'use client';

/**
 * 크레딧 화면 — 분류 pill / 버킷 목록 / 커브(잔존×YTM) / 매수 니즈.
 *
 * ★계산 없음. 활성 필터·버킷 중앙값·커브 점·니즈 매칭은 `kbond_view.py` 가 낸다
 *   (`cr_buckets`·`curve_points`·`cr_sel`·`cr_needs`). 화면은 좌표로 옮겨 그릴 뿐이다.
 *
 * ★[OWNER 2026-09-11] 분류 줄 앞에 국고·통안이 선다. 둘은 계열이 아니라 레인이라
 *   등급 축이 없어서, 고르면 서버가 «만기 버킷» 으로 접어 같은 모양으로 보낸다
 *   (`gov_buckets`·`gov_sel`·`gov_curve`). 화면은 단위(종/건)와 없는 축(니즈·등급
 *   커브)만 달리 말하고, 표는 그대로 쓴다.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';

import { Text } from '@coinbase/cds-web/typography';

import { getView } from '@/lib/api';
import { Heat } from '@/components/Heat';
import type { TtlMode, View } from '@/lib/api';

type Bucket = NonNullable<View['buckets']>[number];
type Offer = NonNullable<View['offers']>[number];
type Need = NonNullable<View['needs']>[number];

const n3 = (v?: number | null) => (v == null ? '—' : v.toFixed(3));
const sbp = (v?: number | null) => (v == null ? '' : `${v > 0 ? '+' : ''}${v.toFixed(1)}`);
const lot = (a?: number | null) => (a == null || !a ? '—' : `${Math.round(a * 10) / 10}억`);
const ttmTxt = (t?: number | null) =>
  t == null ? '' : t < 1 ? `${Math.round(t * 12)}M` : `${t.toFixed(1)}년`;

/** 잔존×YTM 산점도. 서버가 준 점과 민평선을 좌표로만 옮긴다. */
function Curve({ curve, grade }: {
  curve: NonNullable<View['curve']>;
  grade?: View['grade_curve'];
}) {
  const W = 560;
  const H = 260;
  const pad = { l: 44, r: 10, t: 12, b: 24 };
  /* ★`?? []` 는 매 렌더 새 배열을 만든다 — 그대로 useMemo 의존성에 넣으면
     메모가 매번 다시 돈다(린트가 잡았다). 파생값도 메모로 감싼다. */
  const line = useMemo(() => (curve.mp_line ?? []) as number[][], [curve]);
  const pts = useMemo(
    () => (curve.offers ?? []) as { ttm?: number; ytm?: number; bpe?: number; n?: string }[],
    [curve],
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
    const x0 = 0;
    const x1 = Math.max(...xs) || 1;
    let y0 = Math.min(...ys);
    let y1 = Math.max(...ys);
    const m = (y1 - y0) * 0.08 || 0.05;
    y0 -= m;
    y1 += m;
    return { x0, x1, y0, y1 };
  }, [pts, line]);

  if (!box) return <div className="kb-empty">그릴 점이 없습니다</div>;
  const px = (x: number) => pad.l + ((x - box.x0) / (box.x1 - box.x0 || 1)) * (W - pad.l - pad.r);
  const py = (y: number) => H - pad.b - ((y - box.y0) / (box.y1 - box.y0 || 1)) * (H - pad.t - pad.b);

  const path = line
    .filter((p) => p[0] != null && p[1] != null)
    .map((p, i) => `${i ? 'L' : 'M'}${px(p[0]).toFixed(1)},${py(p[1]).toFixed(1)}`)
    .join(' ');

  /* 등급 커브 — 서버가 `credit_matrix` 최신 한 벌에서 골라 준 것이다. */
  const gradePath = (grade?.pts ?? [])
    .filter((p) => p.ttm <= box.x1 && p.y >= box.y0 && p.y <= box.y1)
    .map((p, i) => `${i ? 'L' : 'M'}${px(p.ttm).toFixed(1)},${py(p.y).toFixed(1)}`)
    .join(' ');

  const yTicks = [box.y0, (box.y0 + box.y1) / 2, box.y1];
  const xTicks = [0, box.x1 / 2, box.x1];

  return (
    <svg className="kb-curve" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="잔존 대 YTM">
      {yTicks.map((y) => (
        <g key={`y${y}`}>
          <line x1={pad.l} x2={W - pad.r} y1={py(y)} y2={py(y)} className="kb-grid" />
          <text x={pad.l - 6} y={py(y) + 3} className="kb-axis" textAnchor="end">
            {y.toFixed(2)}
          </text>
        </g>
      ))}
      {xTicks.map((x) => (
        <text key={`x${x}`} x={px(x)} y={H - 8} className="kb-axis" textAnchor="middle">
          {ttmTxt(x)}
        </text>
      ))}
      {path ? <path d={path} className="kb-mpline" /> : null}
      {gradePath ? <path d={gradePath} className="kb-gradeline" /> : null}
      {pts.map((p, i) =>
        p.ttm == null || p.ytm == null ? null : (
          <circle
            key={i}
            cx={px(p.ttm)}
            cy={py(p.ytm)}
            r={3}
            className={`kb-pt ${p.bpe == null ? '' : p.bpe < 0 ? 'dn' : 'up'}`}
          >
            <title>{`${p.n ?? ''} · 잔존 ${ttmTxt(p.ttm)} · ${n3(p.ytm)}${p.bpe != null ? ` · 민평대비 ${sbp(p.bpe)}bp` : ''}`}</title>
          </circle>
        ),
      )}
    </svg>
  );
}

export function Credit({ ttl, onTtl }: { ttl: TtlMode; onTtl?: (t: TtlMode) => void }) {
  const [v, setV] = useState<View | null>(null);
  const [cls, setCls] = useState<string | null>(null);
  const [rt, setRt] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const pull = useCallback(async () => {
    try {
      setV(await getView('cr', ttl, cls ?? undefined, rt ?? undefined));
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : '실패');
    }
  }, [ttl, cls, rt]);

  useEffect(() => {
    void pull();
    const id = setInterval(() => void pull(), 5000);
    return () => clearInterval(id);
  }, [pull]);

  if (err) return <div className="kb-empty">백엔드에 못 붙었습니다 — {err}</div>;
  if (!v) return <div className="kb-empty">부르는 중…</div>;

  const buckets: Bucket[] = v.buckets ?? [];
  const offers: Offer[] = v.offers ?? [];
  const needs: Need[] = v.needs ?? [];
  /* ★[OWNER 2026-09-11] 분류 줄의 «구성» 은 서버가 낸다(`cls_pills`) — 국고·통안이
     앞에 서고 그다음 위험순 계열 여덟이다. 히트맵 행과 같은 축이고, 건수가 0 인
     칸도 빠지지 않는다(줄이 날마다 흔들리면 눈이 자리를 잃는다).
     ⚠예전처럼 «버킷에서 뽑아» 만들면 안 된다 — 그러면 국고·통안이 못 들어오고
       비어 있는 계열이 사라진다. 옛 판으로 되돌릴 때만 아래 한 줄을 쓴다. */
  const pills = v.classes ?? [];
  const govSel = pills.some((p) => p.gov && p.cls === cls);
  const shown = cls ? buckets.filter((b) => b.cls === cls) : buckets;
  const lvl = offers.filter((o) => o.ytm != null);
  const noLvl = offers.filter((o) => o.ytm == null);

  return (
    <div className="kb-credit">
      <div className="kb-card kb-list">
        <div className="kb-ch">
          <Text as="span" font="label2">분류</Text>
          <Text as="span" font="legal" color="fgMuted">
            {govSel
              ? `${cls} · ${buckets.reduce((a, b) => a + (b.n ?? 0), 0)}종`
              : `${v.counts?.cr ?? 0}건`}
          </Text>
        </div>
        <div className="kb-pills">
          <button className={`kb-pill${cls ? '' : ' on'}`} onClick={() => { setCls(null); setRt(null); }}>
            전체
          </button>
          {pills.map((p) => (
            <button
              key={p.cls}
              className={`kb-pill${cls === p.cls ? ' on' : ''}`}
              onClick={() => { setCls(p.cls); setRt(null); }}
              title={p.gov ? `${p.cls} — 등급이 없는 레인이라 만기 버킷으로 접습니다 · ${p.n}종` : `${p.n}건`}
            >
              {p.cls}
            </button>
          ))}
        </div>
        <div className="kb-scroll">
          {shown.map((b) => (
            <button
              key={b.k}
              className={`kb-li cr${cls === b.cls && rt === b.rt ? ' on' : ''}`}
              onClick={() => { setCls(b.cls ?? null); setRt(b.rt ?? null); }}
              title={
                b.nat
                  ? `${b.n}건 중 ${b.nat}건이 «민평에» — 중앙 bp 는 값을 부른 ${b.n - b.nat}건으로 잽니다`
                  : undefined
              }
            >
              <span className="nm">
                {b.cls} {b.rt}
                {b.est ? <b className="kb-badge">집계</b> : null}
              </span>
              {/* ★국고·통안 버킷의 n 은 «건» 이 아니라 «종» 이다 — 칸 값이 종목마다
                  하나씩인 (mid − 민평) 이라서다. 서버가 gov 로 알려 준다. */}
              <span className="num kb-n">{b.n}{b.gov ? '종' : '건'}</span>
              <span className="num">{n3(b.ytm_med)}</span>
              <span className={`num ${b.bp_med == null ? '' : b.bp_med < 0 ? 'sr-down' : 'sr-up'}`}>
                {b.bp_med == null ? '' : `${sbp(b.bp_med)}bp`}
              </span>
            </button>
          ))}
        </div>
      </div>

      <div className="kb-mid">
        <div className="kb-card">
          <div className="kb-ch">
            <Text as="span" font="label2">커브</Text>
            <Text as="span" font="legal" color="fgMuted">
              잔존 × YTM · 민평선 {v.curve?.mp_n ?? 0}종
              {v.grade_curve ? ` · 등급커브 ${v.grade_curve.group}` : ''}
            </Text>
          </div>
          {v.curve ? (
            <Curve curve={v.curve} grade={v.grade_curve} />
          ) : (
            <div className="kb-empty">커브가 없습니다</div>
          )}
        </div>

        <div className="kb-card">
          <div className="kb-ch">
            <Text as="span" font="label2">히트맵</Text>
            <Text as="span" font="legal" color="fgMuted">종별 × 잔존 · 중앙 민평대비</Text>
          </div>
          {v.heat ? <Heat heat={v.heat} /> : null}
        </div>

        <div className="kb-card">
          <div className="kb-ch">
            <Text as="span" font="label2">매수 니즈</Text>
            <Text as="span" font="legal" color="fgMuted">{needs.length}건</Text>
          </div>
          {needs.length ? (
            <table className="kb-tbl">
              <thead>
                <tr>
                  <th className="l">딜러</th>
                  <th className="l">종별</th>
                  <th>잔존</th>
                  <th>수량</th>
                  <th>기준</th>
                </tr>
              </thead>
              <tbody>
                {needs.slice(0, 40).map((b, i) => (
                  <tr key={i}>
                    <td className="l">{b.d}</td>
                    <td className="l kb-n">
                      {b.sec ?? '전체'}
                      {b.rt ? ` ${b.rt}` : ''}
                    </td>
                    <td className="num kb-n">
                      {b.lo != null && b.hi != null ? `${b.lo}~${b.hi}년` : ''}
                    </td>
                    <td className="num">{lot(b.a)}</td>
                    <td className="num kb-n">
                      {b.bo
                        ? `${(b.bo as { n?: string }).n ?? ''} ${sbp((b.bo as { bp?: number }).bp)}bp`
                        : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="kb-empty">
              {govSel ? '국고·통안에는 바스켓이 없습니다' : '살아 있는 니즈가 없습니다'}
            </div>
          )}
        </div>
      </div>

      <div className="kb-right">
        <div className="kb-card">
          <div className="kb-ch">
            <Text as="span" font="label2">오퍼</Text>
            <Text as="span" font="legal" color="fgMuted">
              잔존 순{noLvl.length ? ` · 레벨 미상 ${noLvl.length}` : ''}
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
          {offers.length ? (
            <table className="kb-tbl">
              <thead>
                <tr>
                  <th className="l">종목</th>
                  <th>잔존</th>
                  <th>민평대비</th>
                  <th>YTM</th>
                  <th>수량</th>
                </tr>
              </thead>
              <tbody>
                {lvl.slice(0, 60).map((e, i) => (
                  <tr key={i} title={`${e.d ?? ''}`}>
                    <td className="l">{e.n}</td>
                    <td className="num kb-n">{ttmTxt(e.ttm)}</td>
                    {/* «민평에 팔자» 는 +0.0bp 가 아니라 «민평» 으로 읽어야 한다 —
                        0.0 으로 쓰면 딜러가 정확히 0 을 부른 것처럼 보인다 [OWNER 2026-09-07] */}
                    <td className={`num ${e.atmp ? 'kb-n' : e.bpe == null ? '' : e.bpe < 0 ? 'sr-down' : 'sr-up'}`}>
                      {e.atmp ? '민평' : e.bpe != null ? `${sbp(e.bpe)}bp` : e.won != null ? `${sbp(e.won)}원` : ''}
                    </td>
                    <td className={`num${e.lvl === 'est' ? ' kb-n' : ''}`}>
                      {n3(e.ytm)}
                      {e.lvl && e.lvl !== 'quoted' ? (
                        <b className="kb-badge">{e.lvl === 'conv' ? '환산' : '추정'}</b>
                      ) : null}
                    </td>
                    <td className="num">{lot(e.a)}</td>
                  </tr>
                ))}
                {noLvl.length ? (
                  <tr>
                    <td colSpan={5} className="l kb-n" style={{ paddingTop: 8 }}>
                      ── 레벨 미상 (결과금리 없음) ──
                    </td>
                  </tr>
                ) : null}
                {noLvl.slice(0, 30).map((e, i) => (
                  <tr key={`x${i}`} className="mut">
                    <td className="l">{e.n}</td>
                    <td className="num kb-n">{ttmTxt(e.ttm)}</td>
                    <td className="num kb-n">{e.won != null ? `${sbp(e.won)}원` : ''}</td>
                    <td className="num kb-n">—</td>
                    <td className="num kb-n">{lot(e.a)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="kb-empty">살아 있는 오퍼가 없습니다</div>
          )}
        </div>
      </div>
    </div>
  );
}
