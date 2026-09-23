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
import { Curve } from '@/components/Curve';
import { Heat } from '@/components/Heat';
import type { FeedRow, TtlMode, View } from '@/lib/api';

type Bucket = NonNullable<View['buckets']>[number];
type Offer = NonNullable<View['offers']>[number];
type Need = NonNullable<View['needs']>[number];

const n3 = (v?: number | null) => (v == null ? '—' : v.toFixed(3));
const sbp = (v?: number | null) => (v == null ? '' : `${v > 0 ? '+' : ''}${v.toFixed(1)}`);
const lot = (a?: number | null) => (a == null || !a ? '—' : `${Math.round(a * 10) / 10}억`);
const ttmTxt = (t?: number | null) =>
  t == null ? '' : t < 1 ? `${Math.round(t * 12)}M` : `${t.toFixed(1)}년`;
/** 장중 초 → 시:분:초. `Bonds` 와 같은 셈이다. */
const hms = (s?: number | null) => {
  if (s == null) return '';
  const p2 = (n: number) => String(n).padStart(2, '0');
  return `${p2(Math.floor(s / 3600) % 24)}:${p2(Math.floor((s % 3600) / 60))}:${p2(s % 60)}`;
};

export function Credit({ ttl, onTtl, feed = [] }: {
  ttl: TtlMode;
  onTtl?: (t: TtlMode) => void;
  /** 메시지 테이프용 피드. `page.tsx` 가 이미 들고 있는 것을 내려 받는다 —
   *  접거나 세지 않고 «고르기만» 하므로 서버 계산과 겹치지 않는다. */
  feed?: FeedRow[];
}) {
  const [v, setV] = useState<View | null>(null);
  const [cls, setCls] = useState<string | null>(null);
  const [rt, setRt] = useState<string | null>(null);
  const [crv, setCrv] = useState(10);
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
  /* 메시지 테이프 — 옛 화면의 크레딧 탭에 있던 것을 옮긴다. 고르기만 한다.
     국고·통안 pill 을 고른 동안에는 그 레인 메시지를 쌓는다(화면 이름이 «국고» 인데
     크레딧 메시지가 흐르면 읽는 사람이 속는다). */
  const tapeSec = govSel && cls ? cls : '크레딧/기타';
  const tape = feed.filter((e) => e.sec === tapeSec).slice(-200).reverse();
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
                [
                  b.nat
                    ? `${b.n}건 중 ${b.nat}건이 «민평에» — 중앙 bp 는 값을 부른 ${b.n - b.nat}건으로 잽니다`
                    : '',
                  b.mb ? `매수 니즈에 맞는 오퍼 ${b.mb}건` : '',
                ]
                  .filter(Boolean)
                  .join(' · ') || undefined
              }
            >
              <span className="nm">
                {b.cls} {b.rt}
                {b.est ? <b className="kb-badge">집계</b> : null}
                {/* ★통안 최신물은 민평 적재가 며칠 늦다 — 그 «대비» 는 전일 대비가 아니다.
                    히트맵이 별표로 말하는 것을 이 줄도 말해야 한다 [2026-09-11]. */}
                {b.stale ? (
                  <b className="kb-badge stale" title="민평이 그날 것이 아닙니다 — 전일 대비가 아닙니다">
                    묵음
                  </b>
                ) : null}
              </span>
              {/* ★국고·통안 버킷의 n 은 «건» 이 아니라 «종» 이다 — 칸 값이 종목마다
                  하나씩인 (mid − 민평) 이라서다. 서버가 gov 로 알려 준다. */}
              {/* ★«수요 매칭» 은 옛 화면이 부제에 달고 있던 값이다 — 전환에서 잃으면
                  안 되는 수라 여기 붙인다(2026-09-11 지문 대조에서 드러났다). */}
              <span className="num kb-n">
                {b.n}{b.gov ? '종' : '건'}
                {b.mb ? <span className="kb-mb">수요 {b.mb}</span> : null}
              </span>
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
              {govSel
                ? `잔존 × YTM · 기준선 = 종목 전일 민평 · 민평선 ${v.curve?.mp_n ?? 0}종`
                : `잔존 × YTM · 민평선 ${v.curve?.mp_n ?? 0}종${v.grade_curve ? ` · 등급커브 ${v.grade_curve.group}` : ''}`}
            </Text>
            {/* x축 범위 — 옛 화면과 같은 세 칸이고 기본도 같은 10년이다. */}
            <div className="kb-crv">
              {([[5, '5년'], [10, '10년'], [0, '전체']] as [number, string][]).map(([x, nm]) => (
                <button
                  key={nm}
                  className={`kb-pill${crv === x ? ' on' : ''}`}
                  onClick={() => setCrv(x)}
                >
                  {nm}
                </button>
              ))}
            </div>
          </div>
          {v.curve ? (
            <Curve curve={v.curve} grade={v.grade_curve} range={crv} />
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

        <div className="kb-card">
          <div className="kb-ch">
            <Text as="span" font="label2">메시지</Text>
            <Text as="span" font="legal" color="fgMuted">
              {govSel ? cls : '크레딧'} 전체 {tape.length.toLocaleString()}건
            </Text>
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
            <div className="kb-empty">아직 {govSel ? cls : '크레딧'} 메시지가 없습니다</div>
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
