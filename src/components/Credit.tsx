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
import { useCallback, useEffect, useState } from 'react';

import { Text } from '@coinbase/cds-web/typography';

import { getView } from '@/lib/api';
import { Curve } from '@/components/Curve';
import { Heat } from '@/components/Heat';
import type { FeedRow, TtlMode, View } from '@/lib/api';
import {
  EMDASH, fmtBp, fmtBpUnit, fmtCount, fmtHms, fmtLot, fmtMin, fmtTtm, fmtTtmRange,
  fmtYield,
} from '@/lib/format';
import { Delta } from '@/ui/Delta';
import { ColGroup } from '@/ui/ColGroup';
import { TABLES } from '@/lib/columns';

type Bucket = NonNullable<View['buckets']>[number];
type Offer = NonNullable<View['offers']>[number];
type Need = NonNullable<View['needs']>[number];


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
  /* ★[OWNER 2026-09-28] 「싼 것부터」 — 거르기가 아니라 **보기 한 가지**다.
     처음엔 「값 부른 것만」(거르기)으로 지었다가 **재서 바꿨다**: 표는 잔존 순
     60줄까지만 그리는데 무리 1위들은 책 825개에 흩어져 있어, 걸러도 화면에 뜬
     1위 배지가 **1개**였다(실측). 3분의 2를 감춰도 여전히 «짧은 것 60개» 를 볼 뿐이다.
     ▎그래서 이 단추는 두 가지를 같이 한다 — 「민평에」를 감추고 **싼 것부터 줄 세운다**.
       그러면 표 맨 위가 곧 오늘의 후보 목록이 된다.
     ▎잔존 순은 기본 보기의 규칙(오너)이고 여기서 그대로다. 이 단추는 «누른 동안만»
       다른 순서로 보는 것이고, 누른 상태가 머리줄에 적힌다.
     ▎서버로 안 보낸다 — 이미 받은 줄을 다시 세우는 «보기» 일 뿐이라 책이 안 바뀐다. */
  const [cheap, setCheap] = useState(false);
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
  const lvl0 = offers.filter((o) => o.ytm != null);
  const nAtmp = lvl0.filter((o) => o.atmp).length;
  /* 싸다 = 금리가 높다. 커브 반영값이 있으면 그것으로 줄 세운다(시장 이동을 걷어낸
     뒤라야 «이 종목이» 싼지가 나온다). 없으면 민평대비로 — 짧은 쪽은 둘이 거의 같다. */
  const cheapOf = (o: Offer) => o.bpc ?? o.bpe ?? -Infinity;
  const lvl = cheap
    ? lvl0.filter((o) => !o.atmp).sort((a, z) => cheapOf(z) - cheapOf(a))
    : lvl0;
  const noLvl = offers.filter((o) => o.ytm == null);
  /* ★커브 반영 민평대비 [OWNER 2026-09-28].
     «민평대비» 에는 두 가지가 섞여 있다 — «이 종목이 싸졌다» 와 «오늘 시장이
     움직였다». 서버가 같은 잔존의 국고 커브 이동을 빼서 앞만 남긴 값을 같이 보낸다
     (`kbond_view.curve_move`). 화면은 그 수와 **닻** 을 나란히 적기만 한다 —
     파생된 수는 무엇에서 나왔는지 같이 보여야 믿을 수 있다. */
  const cm = v.curve_move ?? null;
  const cmOn = !!cm?.ok;
  const cmTitle = cmOn
    ? [
        `오늘 국고 커브가 잔존별로 움직인 만큼을 «민평대비» 에서 뺀 값입니다.`,
        `닻 ${cm!.n}칸 (국고 종목의 지금 mid − 전일 민평):`,
        ...(cm!.pts ?? []).map(
          (a) => `  ${fmtTtm(a.ttm)}  ${fmtBpUnit(a.bp)}  ${a.cs.join(',')}`
            + (a.age ? ` (${fmtMin(a.age)} 전)` : ''),
        ),
        `닻보다 짧은 종목은 0 으로 기울여 내립니다 — 국고 책에는 짧은 종목이 없습니다.`,
      ].join('\n')
    : '닻(국고 종목의 지금 mid)이 둘 미만이라 뺄 수 없습니다.';

  return (
    <div className="kb-credit">
      <div className="kb-card">
        <div className="kb-ch">
          <Text as="span" font="label2">분류</Text>
          <Text as="span" font="legal" color="fgMuted" className="kb-ch-meta">
            {/* ★단위는 열 머리가 «한 번» 말한다 [v2 `unitSuffix` 규칙] — 서른 줄이 각자
                `bp` 를 달면 그만큼 숫자가 벌어지고, 숫자를 세로로 견주라고 만든 열에서
                그건 가장 하면 안 되는 일이다. 칸에서 뗀 자리가 종목명으로 간다. */}
            {govSel
              ? `${cls} · ${buckets.reduce((a, b) => a + (b.n ?? 0), 0)}종 · YTM · 민평대비 bp`
              : `${v.counts?.cr ?? 0}건 · YTM · 민평대비 bp`}
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
                  /* ★칸을 늘리지 않는다 — `compare_screens` 가 `.kb-li.cr` 의
                     **자식 넷**을 차례로 읽는다(지문 계약). 그래서 툴팁이 진다. */
                  b.bpc_med != null ? `커브 반영 ${fmtBpUnit(b.bpc_med)}` : '',
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
              <span className="num">{fmtYield(b.ytm_med)}</span>
              <span className="num">
                <Delta v={b.bp_med} />
              </span>
            </button>
          ))}
        </div>
      </div>

      <div className="kb-mid">
        <div className="kb-card">
          <div className="kb-ch">
            <Text as="span" font="label2">커브</Text>
            <Text as="span" font="legal" color="fgMuted" className="kb-ch-meta">
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
            <Text as="span" font="legal" color="fgMuted" className="kb-ch-meta">종별 × 잔존 · 중앙 민평대비</Text>
          </div>
          {v.heat ? <Heat heat={v.heat} /> : null}
        </div>

        <div className="kb-card">
          <div className="kb-ch">
            <Text as="span" font="label2">매수 니즈</Text>
            <Text as="span" font="legal" color="fgMuted" className="kb-ch-meta">{needs.length}건</Text>
          </div>
          {needs.length ? (
            <table className="kb-tbl">
              <ColGroup cols={TABLES.needs} />
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
                      {b.lo != null && b.hi != null ? fmtTtmRange(b.lo, b.hi) : ''}
                    </td>
                    <td className="num">{fmtLot(b.a)}</td>
                    <td className="num kb-n">
                      {b.bo
                        ? `${(b.bo as { n?: string }).n ?? ''} ${fmtBpUnit((b.bo as { bp?: number }).bp)}`
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
              {govSel ? cls : '크레딧'} 전체 {fmtCount(tape.length)}건
            </Text>
          </div>
          {tape.length ? (
            <div className="kb-scroll">
              {tape.map((e) => (
                <div className="kb-tp" key={e.i}>
                  <span className="kb-n">{fmtHms(e.t)}</span>
                  <span className={e.s === 'S' ? 'kb-side-s' : e.s === 'B' ? 'kb-side-b' : undefined}>
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
            {/* ★파생된 수는 «무엇에서 나왔는지» 를 같이 적는다 — 커브 이동·닻 수·
                닻이 덮는 잔존 폭. 이것이 없으면 커브반영 칸은 검산할 수 없는 수다. */}
            <Text as="span" font="legal" color="fgMuted" className="kb-ch-meta" title={cmTitle}>
              {/* ★한 줄을 넘기면 안 된다 — 카드 머리가 두 줄이 되면 나란히 선
                  카드들의 첫 줄이 계단이 진다(v2 얼라인 5). 닻의 «자세한 것»은
                  `title` 이 지고, 보이는 줄은 믿을지 말지 정할 만큼만 적는다:
                  얼마나 뺐나(커브) · 무엇으로 뺐나(닻 수).
                  단위 `bp` 는 옆 칸(민평대비)이 행마다 달고 있어 겹쳐 적지 않는다. */}
              {cheap ? `싼 것부터 ${lvl.length}` : '잔존 순'}
              {noLvl.length ? ` · 미상 ${noLvl.length}` : ''}
              {cmOn
                ? ` · 커브 ${fmtBpUnit(cm!.med)} · 닻 ${cm!.n}`
                : govSel
                  ? ''
                  : ' · 커브 반영 불가'}
            </Text>
            {nAtmp ? (
              <button
                className={`kb-pill${cheap ? ' on' : ''}`}
                onClick={() => setCheap((x) => !x)}
                aria-pressed={cheap}
                title={`「민평에」 ${nAtmp}건을 감추고 싼 것(금리 높은 것)부터 줄 세웁니다.`
                  + ` 그 줄들은 레벨이 아니라 «기준 그 자리» 라 싼 것을 고를 때는 셀 수 없습니다.`
                  + ` 커브 반영값이 있으면 그것으로, 없으면 민평대비로 셉니다.`}
              >
                싼 것부터
              </button>
            ) : null}
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
              <ColGroup cols={TABLES.offers} />
              <thead>
                <tr>
                  <th className="l">종목</th>
                  <th>잔존</th>
                  <th>민평대비</th>
                  <th title={cmTitle}>커브반영</th>
                  <th>YTM</th>
                  <th>수량</th>
                </tr>
              </thead>
              <tbody>
                {lvl.slice(0, 60).map((e, i) => (
                  /* ★순위는 칸을 안 쓴다 — 표는 이미 여섯 칸이고 일곱째를 내면
                      종목 이름이 «…» 만 남는다. 무리의 **1위에만 배지**를 달고
                      나머지 순위는 줄 툴팁이 진다: 훑는 눈에는 «여기» 하나면 되고,
                      따져 볼 때는 마우스를 올린다. */
                  <tr
                    key={i}
                    title={[e.d ?? '', e.pk && e.pn ? `${e.pk} ${e.pn}개 중 ${e.pr}위` : '']
                      .filter(Boolean).join(' · ') || undefined}
                  >
                    <td className="l nm" title={e.n ?? undefined}>
                      {e.n}
                      {e.pr === 1 ? <b className="kb-badge best">1위</b> : null}
                    </td>
                    <td className="num kb-n">{fmtTtm(e.ttm)}</td>
                    {/* «민평에 팔자» 는 +0.0bp 가 아니라 «민평» 으로 읽어야 한다 —
                        0.0 으로 쓰면 딜러가 정확히 0 을 부른 것처럼 보인다 [OWNER 2026-09-07] */}
                    {/* ★방향색은 **한 칸에만** 준다 [2026-09-28].
                        두 칸이 나란히 붉고 푸르면 눈이 둘 다 읽어야 하고, 그러면
                        어느 쪽이 «읽는 수» 인지 화면이 말하지 않는 셈이 된다.
                        왼쪽은 문면에서 든 값이라 잉크, 오른쪽이 판단할 값이다. */}
                    <td className={`num${e.atmp ? ' kb-n' : ''}`}>
                      {e.atmp ? (
                        '민평'
                      ) : e.bpe != null ? (
                        <Delta v={e.bpe} unit="bp" ink />
                      ) : e.won != null ? (
                        <Delta v={e.won} unit="원" ink />
                      ) : (
                        ''
                      )}
                    </td>
                    {/* 뺄 수 없으면 «—» 다(0 이 아니다) — 닻 밖이거나 닻이 모자란다.
                        `title` 이 그 줄에서 실제로 뺀 양을 말한다. */}
                    <td
                      className="num"
                      title={
                        e.bpc != null && e.cmv != null
                          ? `${fmtBp(e.bpe)} − (커브 ${fmtBp(e.cmv)}) = ${fmtBp(e.bpc)}bp`
                          : cmOn
                            ? '닻이 덮는 잔존 밖입니다'
                            : undefined
                      }
                    >
                      {e.bpc != null ? <Delta v={e.bpc} /> : EMDASH}
                    </td>
                    <td className={`num${e.lvl === 'est' ? ' kb-n' : ''}`}>
                      {fmtYield(e.ytm)}
                      {e.lvl && e.lvl !== 'quoted' ? (
                        <b className="kb-badge">{e.lvl === 'conv' ? '환산' : '추정'}</b>
                      ) : null}
                    </td>
                    <td className="num">{fmtLot(e.a)}</td>
                  </tr>
                ))}
                {noLvl.length ? (
                  <tr>
                    <td colSpan={6} className="l kb-n" style={{ paddingTop: 8 }}>
                      ── 레벨 미상 (결과금리 없음) ──
                    </td>
                  </tr>
                ) : null}
                {noLvl.slice(0, 30).map((e, i) => (
                  <tr key={`x${i}`} className="mut">
                    <td className="l nm" title={e.n ?? undefined}>{e.n}</td>
                    <td className="num kb-n">{fmtTtm(e.ttm)}</td>
                    <td className="num kb-n">{e.won != null ? <Delta v={e.won} unit="원" ink /> : ''}</td>
                    <td className="num kb-n">{EMDASH}</td>
                    <td className="num kb-n">{EMDASH}</td>
                    <td className="num kb-n">{fmtLot(e.a)}</td>
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
