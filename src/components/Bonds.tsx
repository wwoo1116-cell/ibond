'use client';

/**
 * 종목 화면 — 좌 목록 / 중 요약 / 우 호가창·딜러.
 *
 * ★이 파일에는 계산이 없다. 활성 필터·무크로스·최우선·사다리 칸·합계·막대 잣대는
 *   전부 `kbond_view.py` 가 내고 `/api/view?code=` 로 온다. 여기서 다시 접으면
 *   규칙이 두 벌이 되고 언젠가 갈라진다 [OWNER 2026-09-03 「계산과 집계는 서버」].
 *
 *   막대 «폭» 과 나이 «칠» 은 값이 아니라 표현이라 여기서 한다.
 */
import { Fragment, useCallback, useEffect, useState } from 'react';

import { Text } from '@coinbase/cds-web/typography';

import { getView } from '@/lib/api';
import type { FeedRow, Lane, TtlMode, View } from '@/lib/api';

type ObLadder = NonNullable<View['ob']>;
type ObLevel = NonNullable<ObLadder['levels']>[number];
type ObSide = NonNullable<ObLevel['S']>;
type BondRow = NonNullable<View['rows']>[number];

const n3 = (v?: number | null) => (v == null ? '—' : v.toFixed(3));
const p2 = (n: number) => String(n).padStart(2, '0');
const hms = (t: number) =>
  `${p2(Math.floor(t / 3600))}:${p2(Math.floor((t % 3600) / 60))}:${p2(t % 60)}`;
/** 수량 기본단위 100억 [OWNER] */
const lot = (a?: number | null) => (a == null || !a ? '—' : `${Math.round(a * 10) / 10}억`);
const sbp = (v?: number | null) => (v == null ? '' : `${v > 0 ? '+' : ''}${v.toFixed(1)}bp`);

/** 나이 → 바램 단계. 옛 화면의 ageCls 와 같은 문턱(5분·15분). */
function ageCls(sec: number): '' | 'ag1' | 'ag2' {
  if (sec <= 300) return '';
  return sec <= 900 ? 'ag1' : 'ag2';
}
const ageTxt = (sec: number) =>
  sec < 60 ? `${Math.round(sec)}초` : sec < 3600 ? `${Math.round(sec / 60)}분` : `${(sec / 3600).toFixed(1)}시간`;

/** 사다리 한 칸의 한 면. 폭은 서버가 준 잣대(basis·mx)로만 정한다. */
function Cell({ sd, side, basis, mx, T }: {
  sd: ObSide | null | undefined;
  side: 'S' | 'B';
  basis: string;
  mx: number;
  T: number;
}) {
  if (!sd) return <div className={`kb-q ${side === 'S' ? 'l' : 'r'}`} />;
  const v = basis === 'amt' ? sd.amt : sd.n;
  const w = Math.max(4, Math.round((100 * v) / (mx || 1)));
  const age = T - sd.fresh;
  const allDflt = sd.amt > 0 && sd.dflt === sd.n;
  const tail = sd.odd ? ' +자투리' : sd.unk ? ' +?' : '';
  const txt = sd.amt ? lot(sd.amt) + tail : sd.odd ? '자투리' : '?';
  const who = (sd.who ?? []).filter(Boolean).join(', ');
  // v12 체결 귀속 — 이 칸에서 실제로 붙은 호가. 표시만 하고 지우지 않는다.
  const hit = sd.hit ?? 0;
  const hitAge = sd.fhit ? T - sd.fhit : 0;
  return (
    <div
      className={`kb-q ${side === 'S' ? 'l' : 'r'}`}
      title={`${who} · ${ageTxt(age)} 전${allDflt ? ' · 표기 없음 → 기본단위 100억' : ''}${
        hit ? ` · 이 레벨 체결 ${hit}건 (${ageTxt(hitAge)} 전)` : ''}`}
    >
      <i style={{ width: `${w}%` }} />
      <span className={allDflt ? 'od' : undefined}>{txt}</span>
      <span className="kb-n">{sd.n}</span>
      {hit ? <b className="hit" /> : null}
    </div>
  );
}

function Ladder({ ob, T }: { ob: ObLadder; T: number }) {
  const levels = ob.levels ?? [];
  const imp = ob.implied ?? [];
  if (!levels.length && !imp.length) {
    return <div className="kb-empty">살아 있는 호가가 없습니다</div>;
  }
  const asks: ObLevel[] = [];
  const bids: ObLevel[] = [];
  for (const L of levels) {
    if (L.S) asks.push(L);
    else if (L.B) bids.push(L);
    else if (L.blank === 'b') bids.push(L);
    else if (L.blank === 'a') asks.push(L);
  }
  const best = ob.best ?? {};
  const spTxt =
    best.spread_bp != null
      ? `스프레드 ${best.spread_bp.toFixed(1)}bp · mid ${n3(best.mid)}`
      : (ob.sum?.na ?? 0)
        ? '매도 호가만 있습니다'
        : (ob.sum?.nb ?? 0)
          ? '매수 호가만 있습니다'
          : '';
  const row = (L: ObLevel, side: 'a' | 'b') => (
    <div key={`${side}${L.y}`} className={`kb-obr ${side} ${ageCls(T - (L.S?.fresh ?? L.B?.fresh ?? T))}`}>
      {side === 'a' ? (
        <Cell sd={L.S} side="S" basis={ob.basis} mx={ob.mx} T={T} />
      ) : (
        <div className="kb-q l" />
      )}
      <div className={`kb-p${L.S || L.B ? '' : ' mut'}`}>
        {L.y.toFixed(3)}
        {L.atmp ? <span className="kb-badge">민평</span> : null}
      </div>
      {side === 'b' ? (
        <Cell sd={L.B} side="B" basis={ob.basis} mx={ob.mx} T={T} />
      ) : (
        <div className="kb-q r" />
      )}
    </div>
  );
  return (
    <div className="kb-ob">
      <div className="kb-obh">
        <span>매도 잔량</span>
        <span>금리</span>
        <span>매수 잔량</span>
      </div>
      {asks.map((L) => row(L, 'a'))}
      <div className="kb-obsp">{spTxt}</div>
      {bids.map((L) => row(L, 'b'))}
      <div className="kb-obt">
        <span>
          매도 합 <b>{lot(ob.sum?.a)}</b> <span className="kb-n">{ob.sum?.na}건</span>
        </span>
        <span className="kb-n">막대 = {ob.basis === 'amt' ? '수량' : '호가 건수'}</span>
        <span>
          매수 합 <b>{lot(ob.sum?.b)}</b> <span className="kb-n">{ob.sum?.nb}건</span>
        </span>
      </div>
    </div>
  );
}

function Dealers({ d, T }: { d: NonNullable<View['dealers']>; T: number }) {
  const rows = d.rows ?? [];
  if (!rows.length) return <div className="kb-empty">살아 있는 호가가 없습니다</div>;
  return (
    <table className="kb-tbl">
      <thead>
        <tr>
          <th className="l">딜러</th>
          <th>매도</th>
          <th>매수</th>
          <th>나이</th>
          <th title="오늘 이 종목 호가 건수">오늘</th>
        </tr>
      </thead>
      <tbody>
        {rows.slice(0, 30).map((r) => (
          <tr key={r.k ?? r.d ?? ''} title={r.d ?? ''}>
            <td className="l">{r.d}</td>
            <td className={`num${r.S?.y != null && r.S.y === d.fa_y ? ' best' : ''}`}>
              {r.S ? (r.S.y != null ? n3(r.S.y) : r.S.atmp ? '민평' : '—') : '·'}
            </td>
            <td className={`num${r.B?.y != null && r.B.y === d.fb_y ? ' best' : ''}`}>
              {r.B ? (r.B.y != null ? n3(r.B.y) : r.B.atmp ? '민평' : '—') : '·'}
            </td>
            <td className="num kb-n">{ageTxt(T - r.fresh)}</td>
            <td className="num kb-n">{r.n || ''}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** 시세 — 서버가 준 표본과 세로 범위를 좌표로만 옮긴다.
 *  ★[OWNER] 전일 민평이 정중앙을 지난다. 그 대칭 범위는 `px_series` 가 낸 lo/hi 다. */
function PxChart({ px }: { px: NonNullable<View['px']> }) {
  const W = 900;
  const H = 260;
  const AB = (px.act ?? []).length ? 22 : 0;
  const pad = { l: 4, r: 52, t: 10, b: 18 + AB };
  const pts = px.pts ?? [];
  if (px.note || pts.length < 2 || px.lo == null || px.hi == null) {
    return <div className="kb-empty">{px.note ?? '표본이 모자랍니다'}</div>;
  }
  const t0 = px.t0 ?? pts[0].t;
  const t1 = px.t1 ?? pts[pts.length - 1].t;
  const X = (t: number) => pad.l + ((W - pad.l - pad.r) * (t - t0)) / (t1 - t0 || 1);
  const Y = (v: number) => pad.t + (H - pad.t - pad.b) * (1 - (v - px.lo!) / (px.hi! - px.lo! || 1));
  const path = (key: 'mid' | 'a' | 'b') => {
    let d = '';
    let pen = false;
    for (const p of pts) {
      const v = p[key];
      if (v == null) { pen = false; continue; }
      d += `${pen ? 'L' : 'M'}${X(p.t).toFixed(1)},${Y(v).toFixed(1)}`;
      pen = true;
    }
    return d;
  };
  const ticks = [0, 1, 2, 3].map((i) => px.lo! + ((px.hi! - px.lo!) * i) / 3);
  const hours: number[] = [];
  for (let s = Math.ceil(t0 / 3600) * 3600; s <= t1; s += 3600) hours.push(s);
  const mxA = Math.max(1, ...(px.act ?? []).map((a) => a.tot));
  const bw = Math.max(2, X(t0 + (px.bin || 600)) - X(t0) - 1);

  return (
    <svg className="kb-px" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="시세">
      {ticks.map((v) => (
        <g key={v}>
          <line x1={pad.l} x2={W - pad.r} y1={Y(v)} y2={Y(v)} className="kb-grid" />
          <text x={W - pad.r + 5} y={Y(v) + 3} className="kb-axis">{v.toFixed(3)}</text>
        </g>
      ))}
      {hours.map((s) => (
        <text key={s} x={Math.max(pad.l, X(s))} y={H - 4} className="kb-axis">
          {`${p2(Math.floor(s / 3600))}:${p2(Math.floor((s % 3600) / 60))}`}
        </text>
      ))}
      {px.mp != null ? (
        <>
          <line x1={pad.l} x2={W - pad.r} y1={Y(px.mp)} y2={Y(px.mp)} className="kb-mpref" />
          <text x={W - pad.r + 5} y={Y(px.mp) + 3} className="kb-axis mp">민평</text>
        </>
      ) : null}
      {(px.act ?? []).map((a) => {
        const h = ((AB - 4) * a.n) / mxA;
        return h <= 0 ? null : (
          <rect key={a.t} x={X(a.t)} y={H - 18 - h} width={bw} height={h} className="kb-actbar">
            <title>{`${p2(Math.floor(a.t / 3600))}:${p2(Math.floor((a.t % 3600) / 60))} · ${a.n}건`}</title>
          </rect>
        );
      })}
      <path d={path('a')} className="kb-pxask" />
      <path d={path('b')} className="kb-pxbid" />
      <path d={path('mid')} className="kb-pxmid" />
    </svg>
  );
}

export function Bonds({ lane, ttl, onTtl, feed = [] }: {
  lane: Lane;
  ttl: TtlMode;
  onTtl?: (t: TtlMode) => void;
  feed?: FeedRow[];
}) {
  const [v, setV] = useState<View | null>(null);
  const [code, setCode] = useState<string | null>(null);
  const [agg, setAgg] = useState(0);
  const [err, setErr] = useState<string | null>(null);

  const pull = useCallback(async () => {
    try {
      const j = await getView(lane, ttl, undefined, undefined, code ?? undefined, agg);
      setV(j);
      setErr(null);
      /* 고른 것이 없으면 서버 목록의 «오늘 값이 있는» 첫 종목을 잡는다. */
      if (!code) {
        const first = (j.rows ?? []).find((r) => r.fa || r.fb) ?? (j.rows ?? [])[0];
        if (first) setCode(first.c);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : '실패');
    }
  }, [lane, ttl, code, agg]);

  /* ★레인이 바뀌면 고른 종목을 놓는다. 안 놓으면 통안에서 고른 코드가 국민주택에
     그대로 남아 «헤더는 —, 메시지는 남의 종목» 이 된다(실측 2026-09-04). */
  useEffect(() => {
    setCode(null);
  }, [lane]);

  useEffect(() => {
    void pull();
    const id = setInterval(() => void pull(), 5000);
    return () => clearInterval(id);
  }, [pull]);

  if (err) return <div className="kb-empty">백엔드에 못 붙었습니다 — {err}</div>;
  if (!v) return <div className="kb-empty">부르는 중…</div>;

  const rows: BondRow[] = v.rows ?? [];
  const sel = rows.find((r) => r.c === code) ?? null;
  /* 피드에서 이 종목만 고른다. 접거나 세지 않으니 서버 계산과 겹치지 않는다. */
  const tape = code ? feed.filter((e) => e.code === code).slice(-200).reverse() : [];
  const T = v.T;
  /* 레벨 없는 «관심» — 서버가 이미 TTL 로 거르고 최신순으로 준다 [OWNER 2026-09-07] */
  const ax = v.axes ?? [];
  /* 오늘 날짜 — 통안 민평이 묵었는지 판정한다 [OWNER 2026-09-07] */
  const todayYmd = new Date().toISOString().slice(0, 10);
  /* ★[OWNER 2026-09-03] 「지표물이 뭔지 안 보인다」 — 오늘 호가가 없어도 지표물·
     차기지표물은 커브의 기준이라 맨 위에 고정한다. 그 아래가 «오늘 활동», 그 아래가
     «어제». 어제 구획은 «무엇이 돌았나» 가 요점이라 활동 순으로 세운다(체결 먼저).
     ⚠옛 화면에는 이 세 구획이 있는데 여기에는 없어서 목록이 통째로 만기순이었다 —
       2026-09-11 지문 대조에서 15줄이 전부 어긋나며 드러났다. */
  const pinned = rows.filter((r) => r.bench || r.next);
  const todayRows = rows.filter((r) => r.today && !r.bench && !r.next);
  const ydayRows = rows
    .filter((r) => !r.today && !r.bench && !r.next)
    .sort((a, b) => {
      const f = (x: BondRow) => ((x.pv as { fill?: number | null } | undefined)?.fill != null ? 1 : 0);
      const n = (x: BondRow) => (x.pv as { n?: number } | undefined)?.n ?? 0;
      return f(b) - f(a) || n(b) - n(a);
    });
  const prevDate = (v.rows?.find((r) => r.pv) as { pv?: { date?: string } } | undefined)?.pv?.date;
  const sections = [
    pinned.length ? { head: '지표물 · 차기지표물', list: pinned } : null,
    { head: `오늘 활동${todayRows.length ? '' : ' 없음'}`, list: todayRows },
    ydayRows.length ? { head: `어제${prevDate ? ` (${prevDate})` : ''} · 활동 순`, list: ydayRows } : null,
  ].filter((x): x is { head: string; list: BondRow[] } => x != null);

  return (
    <div className="kb-bonds">
      <div className="kb-card kb-list">
        <div className="kb-ch">
          <Text as="span" font="label2">종목</Text>
          <Text as="span" font="legal" color="fgMuted">{rows.length}종</Text>
        </div>
        <div className="kb-scroll">
          {sections.map(({ head, list }) => (
            <Fragment key={head}>
              <div className="kb-sec">{head}</div>
              {list.map((r) => {
            /* ★오늘 호가가 없는 줄은 «어제 마지막 수준» 을 흐리게 보여 준다 — 옛 화면이
               그렇게 한다(prow). 여기서는 «—» 로 비워 두고 있었다: 지표물은 오늘 값이
               없는 날이 흔해서 커브의 기준이 통째로 빈칸으로 보였다(2026-09-11 지문
               대조에서 26-10 한 줄이 남아 드러났다). */
            const pv = (r.pv ?? {}) as {
              mid?: number | null; fill?: number | null; a?: number | null;
              b?: number | null; mp?: number | null; n?: number | null;
            };
            const val = r.today ? r.mid : (pv.mid ?? pv.fill ?? pv.a ?? pv.b ?? null);
            const mpv = r.mp ?? pv.mp ?? null;
            const dbp = val != null && mpv != null ? (val - mpv) * 100 : null;
            return (
            <button
              key={r.c}
              className={`kb-li2${r.c === code ? ' on' : ''}${r.today ? '' : ' mut'}`}
              onClick={() => setCode(r.c)}
            >
              {/* 두 줄 — 옛 화면과 같다. 한 줄에 밀어 넣으면 배지가 잘린다(실측). */}
              <span className="nm">
                {r.nm}
                {/* ★통안은 딜러가 «구구삼통»·«구통» 으로 부른다 — 만기 표기보다 이 이름이
                    먼저 읽힌다. 옛 화면도 배지로 달아 둔다. */}
                {r.alias ? <b className="kb-badge al">{r.alias}</b> : null}
                {r.bench ? <b className="kb-badge">지표</b> : null}
                {r.next ? <b className="kb-badge">차기</b> : null}
                {!r.today && pv.fill != null ? <b className="kb-badge">어제 체결</b> : null}
                {/* ★[OWNER 2026-09-07] 통안 민평 적재가 멈추면 최대 30일 전 값을 끌어 쓴다.
                    그러면 «전일 민평 대비» 가 아니므로 그 사실을 행에 적는다. */}
                {r.mpd && v.now && r.mpd !== todayYmd ? (
                  <b className="kb-badge stale" title={`민평 기준일 ${r.mpd} — 전일 민평이 아닙니다`}>
                    민평 {r.mpd.slice(5)}
                  </b>
                ) : null}
              </span>
              <span className="v">{n3(val)}</span>
              <span className="sub">
                {r.ten}
                {r.mat ? ` · ${r.mat}` : ''}
                {r.today && r.n ? ` · ${r.n}건` : ''}
                {!r.today && pv.n ? ` · 어제 ${pv.n}건` : ''}
              </span>
              <span className={`d ${r.today ? (dbp != null && dbp < 0 ? 'sr-down' : 'sr-up') : ''}`}>
                {dbp != null ? sbp(dbp) : ''}
              </span>
            </button>
            );
          })}
            </Fragment>
          ))}
        </div>
      </div>

      <div className="kb-mid">
        <div className="kb-card">
          <div className="kb-ch">
            <Text as="span" font="label2">{sel?.nm ?? '—'}</Text>
            {sel?.alias ? <b className="kb-badge al">{sel.alias}</b> : null}
            <Text as="span" font="legal" color="fgMuted">
              {sel?.full && sel.full !== sel.nm ? sel.full : (sel?.ten ?? '')}
            </Text>
          </div>
          <div className="kb-big">{n3(sel?.mid)}</div>
          <div className="kb-sub">
            {sel?.mid != null && sel?.mp != null
              ? `민평 ${n3(sel.mp)} 대비 ${sbp((sel.mid - sel.mp) * 100)}`
              : '민평 대비를 낼 수 없습니다'}
          </div>
          {/* 옛 화면과 같은 네 칸 — 오퍼·비드·스프레드·당일 체결 */}
          <div className="kb-quad">
            <div>
              <span className="kb-n">매도 (오퍼)</span>
              <b className="sr-down">{n3(sel?.fa?.y)}</b>
            </div>
            <div>
              <span className="kb-n">매수 (비드)</span>
              <b className="sr-up">{n3(sel?.fb?.y)}</b>
            </div>
            <div>
              <span className="kb-n">스프레드</span>
              <b>{v.ob?.best?.spread_bp != null ? `${v.ob.best.spread_bp.toFixed(1)}bp` : '—'}</b>
            </div>
            <div>
              <span className="kb-n">당일 체결</span>
              <b>
                {sel?.fill ? n3((sel.fill as { y?: number }).y) : '—'}
                {sel?.fill ? (
                  <span className="kb-n"> {hms((sel.fill as { t?: number }).t ?? 0)}</span>
                ) : null}
              </b>
            </div>
          </div>
          <div className="kb-sub2">
            만기 {sel?.mat || '—'} · 오늘 호가 {sel?.n ?? 0}건
            {sel?.hn ? ` · mid 표본 ${sel.hn}` : ''}
          </div>
        </div>

        <div className="kb-card">
          <div className="kb-ch">
            <Text as="span" font="label2">시세</Text>
            <Text as="span" font="legal" color="fgMuted">
              {v.px?.mp != null ? `민평 ${n3(v.px.mp)} 중앙` : 'mid 이력'}
            </Text>
          </div>
          {v.px ? <PxChart px={v.px} /> : <div className="kb-empty">종목을 고르세요</div>}
        </div>

        <div className="kb-card">
          <div className="kb-ch">
            <Text as="span" font="label2">메시지</Text>
            <Text as="span" font="legal" color="fgMuted">이 종목 {tape.length}건</Text>
          </div>
          {tape.length ? (
            <div className="kb-scroll">
              {tape.map((e) => (
                <div className="kb-tp" key={e.i}>
                  <span className="kb-n">{hms(e.t)}</span>
                  <span className={e.s === 'S' ? 'sr-down' : e.s === 'B' ? 'sr-up' : undefined}>
                    {e.s === 'S' ? '매도' : e.s === 'B' ? '매수' : ''}
                  </span>
                  <span className="kb-tpr">{e.raw}</span>
                  <span className="kb-n">{e.d}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="kb-empty">이 종목 메시지가 아직 없습니다</div>
          )}
        </div>

        {v.swap ? (
          <div className="kb-card">
            <div className="kb-ch">
              <Text as="span" font="label2">교체</Text>
              <Text as="span" font="legal" color="fgMuted">
                {v.swap.n}건 · 신형−구형 bp
              </Text>
            </div>
            {(v.swap.pairs ?? []).map((p) => {
              /* 레벨은 신형−구형 bp 다. 아웃라이트처럼 ×100 하지 않는다. */
              const leg = (e: Record<string, unknown>, side: 'a' | 'b', i: number) => {
                const who = `${(e.d as string) ?? ''}${e.kind === 'AXE' ? ' · 관심' : ''}`;
                const amt = lot(e.a as number | null);
                const y = e.y == null ? '—' : `${sbp(e.y as number)}bp`;
                return (
                  <div key={`${side}${i}`} className={`kb-swr ${side}`}>
                    <span className="w">{side === 'a' ? `${amt} ${who}` : ''}</span>
                    <span className="lv">{y}</span>
                    <span className="w r">{side === 'b' ? `${who} ${amt}` : ''}</span>
                  </div>
                );
              };
              return (
                <div key={p.pair ?? ''} className="kb-swap">
                  <div className="kb-obh">
                    <span>오퍼(신형 매도)</span>
                    <span>{p.pair}</span>
                    <span>비드(신형 매수)</span>
                  </div>
                  {(p.asks ?? []).map((e, i) => leg(e as Record<string, unknown>, 'a', i))}
                  {p.spread_bp != null ? (
                    <div className="kb-obsp">스프레드 {p.spread_bp.toFixed(1)}bp</div>
                  ) : null}
                  {(p.bids ?? []).map((e, i) => leg(e as Record<string, unknown>, 'b', i))}
                </div>
              );
            })}
          </div>
        ) : null}
      </div>

      <div className="kb-right">
        <div className="kb-card">
          <div className="kb-ch">
            <Text as="span" font="label2">호가</Text>
            <select
              className="kb-sel"
              value={String(agg)}
              onChange={(e) => setAgg(Number(e.target.value))}
              title="호가 집계 — 국내 HTS 처럼 빈 칸 포함 균일 격자"
            >
              <option value="0">원호가</option>
              <option value="0.5">0.5bp</option>
              <option value="1">1bp</option>
              <option value="2.5">2.5bp</option>
            </select>
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
          {v.ob ? <Ladder ob={v.ob} T={T} /> : <div className="kb-empty">종목을 고르세요</div>}
        </div>

        <div className="kb-card">
          <div className="kb-ch">
            <Text as="span" font="label2">딜러</Text>
            <Text as="span" font="legal" color="fgMuted">
              {v.dealers ? `${v.dealers.n}곳 · 양면 ${v.dealers.n_both}` : ''}
            </Text>
          </div>
          {v.dealers ? <Dealers d={v.dealers} T={T} /> : null}
        </div>

        {/* ★[OWNER 2026-09-07] 레벨 없는 «관심» — 책이 아니다.
            종목·방향은 정해졌는데 값이 없는 호가(「19-1 사자」·「25.4.2통 팔자」).
            09-01 판정대로 사다리·최우선에는 안 올리고 여기서만 보인다. */}
        {ax.length ? (
          <div className="kb-card">
            <div className="kb-ch">
              <Text as="span" font="label2">관심</Text>
              <Text as="span" font="legal" color="fgMuted">
                레벨 없는 호가 {ax.length}건 · 책에는 안 들어갑니다
              </Text>
            </div>
            <div className="kb-axl">
              {ax.slice(0, 24).map((e, i2) => (
                <div className="kb-li ax" key={i2} title={`${e.d ?? ''} · ${ageTxt(T - e.t)} 전`}>
                  <span className="nm">{e.n}</span>
                  {/* ★방향색은 데스크 관례 — 매수 빨강(sr-up) · 매도 파랑(sr-down) */}
                  <span className={`num ${e.s === 'B' ? 'sr-up' : 'sr-down'}`}>
                    {e.s === 'B' ? '사자' : '팔자'}
                  </span>
                  <span className="num kb-n">{e.a ? `${e.a}억` : ''}</span>
                  <span className="num kb-n">{ageTxt(T - e.t)}</span>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
