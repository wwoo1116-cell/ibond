'use client';

/**
 * 셸 — 세그먼트 탭 + 화면.
 *
 * ★이 앱의 규율은 «화면은 그리기만 한다» 다. 활성 필터·무크로스·최우선·중앙값·
 *   히트맵 칸은 전부 백엔드(`kbond_view.py`)가 계산해 `/api/view` 로 준다.
 *   여기서 다시 계산하면 규칙이 두 벌이 되고, 그 둘은 언젠가 갈라진다.
 *
 * ★배치·이름·순서는 옛 화면(ibond)을 그대로 따랐다 [OWNER 2026-09-04 「원래 ibond
 *   랑 유사하게」]. 트레이더가 이미 그 순서로 읽고 있어서, 새 화면이 더 «낫게»
 *   배열하면 그건 개선이 아니라 이사 비용이다.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { Box, HStack } from '@coinbase/cds-web/layout';
import { Text } from '@coinbase/cds-web/typography';
import { Button } from '@coinbase/cds-web/buttons';

import { DEFAULT_API, apiBase, getFeed, getHealth, getView, setApi, url } from '@/lib/api';
import type { FeedRow, TtlMode, View } from '@/lib/api';
import { useWatch, watchKey } from '@/lib/watch';
import { Feed } from '@/components/Feed';
import { Bonds } from '@/components/Bonds';
import { Credit } from '@/components/Credit';
import { Trends } from '@/components/Trends';
import { Heat } from '@/components/Heat';
import { Setup } from '@/components/Setup';

type Conn = 'booting' | 'live' | 'stale' | 'setup';

/** 옛 화면과 같은 이름·같은 순서다. 숫자는 서버가 준 `counts` 를 그대로 쓴다. */
type Tab = 'main' | 'dyn' | 'ktb' | 'msb' | 'nhb' | 'cr';
const TABS: [Tab, string, string][] = [
  ['main', '메인', 'main'],
  ['dyn', '동향', 'dyn'],
  ['ktb', '국고', 'ktb'],
  ['msb', '통안', 'msb'],
  ['nhb', '국민주택', 'nhb'],
  ['cr', '크레딧', 'cr'],
];

const p2 = (n: number) => String(n).padStart(2, '0');

/** 피드 필터 — 옛 화면의 둘째 줄. 세는 것은 «고르기» 라 화면 몫이다(접지 않는다).
 *
 * ★묶음은 옛 화면 `KIND` 표 그대로다(`kbond_live.html:531`):
 *   호가 = QUOTE **만** · 문의 = AXE(관심) + INQUIRY · 미해석 = THANKS + OTHER.
 *   처음에 AXE 를 호가에 넣었다가 숫자가 어긋났다(호가 2,760 대 원본 2,491).
 *   새 유형 셋(NOTICE·EVAL·STATE)은 호가가 아니므로 «미해석» 쪽에 둔다.
 */
type Filt = 'all' | 'q' | 'c' | 'ask' | 'etc';
const ETC = new Set(['THANKS', 'OTHER', 'NOTICE', 'EVAL', 'STATE']);
const FILTS: [Filt, string, (k?: string | null) => boolean][] = [
  ['all', '전체', () => true],
  ['q', '호가', (k) => k === 'QUOTE'],
  ['c', '체결', (k) => k === 'CONFIRM'],
  ['ask', '문의', (k) => k === 'AXE' || k === 'INQUIRY'],
  ['etc', '미해석', (k) => ETC.has(k ?? '')],
];

export default function Page() {
  const [rows, setRows] = useState<FeedRow[]>([]);
  const [conn, setConn] = useState<Conn>('booting');
  const [tab, setTab] = useState<Tab>('main');
  const [nMsg, setNMsg] = useState(0);
  const [ref, setRef] = useState<View | null>(null);
  const [clock, setClock] = useState('');
  const [filt, setFilt] = useState<Filt>('all');
  const [ttl, setTtl] = useState<TtlMode>('def');
  const [alarm, setAlarm] = useState(false);
  const { watch } = useWatch();
  const seen = useRef(0);
  const maxI = useRef(0);
  const lastBeat = useRef(0);

  /** 스크롤백은 서버가 하루치를 들고 있다 — 열자마자 한 번 당겨 온다.
   *
   * ★[2026-09-22 수리] 겹침을 «갱신 함수 안에서» 거른다. 예전에는 바깥 `rows`
   *   를 닫아 걸러서, SSE 가 백필보다 먼저 닿으면 그 겹침을 못 봤다 — 백필이
   *   떠날 때의 `rows` 는 비어 있었기 때문이다. SSE 첫 프레임이 `stream[-250:]`
   *   을 싣고 오므로 «맨 아래 250줄이 두 번 그려지는» 꼴로 늘 재현됐다
   *   (실측: 3,000줄을 당겼는데 3,252줄이 섰다). 호가창에서 같은 호가가 둘로
   *   보이는 것은 배치 문제가 아니라 값의 문제다.
   */
  const backfill = useCallback(async () => {
    const j = await getFeed(0, 3000);
    const got = j.feed ?? [];
    if (!got.length) return;
    setRows((prev) => {
      const have = new Set(prev.map((e) => e.i));
      const add = got.filter((e) => !have.has(e.i));
      if (!add.length) return prev;
      return [...prev, ...add].sort((a, b) => a.i - b.i).slice(-6000);
    });
    maxI.current = Math.max(maxI.current, j.n_seq ?? 0);
  }, []);

  /* 기동: 백엔드가 살아 있으면 붙고, 아니면 설정 화면. */
  useEffect(() => {
    let live = true;
    getHealth()
      .then(() => {
        if (!live) return;
        setConn('live');
        void backfill();
      })
      .catch(() => live && setConn('setup'));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* 탭 숫자와 메인 히트맵은 같은 응답에서 온다 — 한 번만 부른다. */
  useEffect(() => {
    if (conn === 'setup' || conn === 'booting') return;
    let live = true;
    const pull = () => {
      getView('ktb', ttl)
        .then((v) => live && setRef(v))
        .catch(() => undefined);
    };
    pull();
    const id = setInterval(pull, 5000);
    return () => {
      live = false;
      clearInterval(id);
    };
  }, [conn, ttl]);

  /* 서버 시각. 옛 화면의 큰 시계 자리다.
   *
   * ★기준점은 «하트비트가 실어 보내는 서버 시각» 이다. 옛 판이 그렇게 한다
   *   (kbond_live.py: 「시계와 생존 신호를 겸한다」).
   * ★책의 T 를 기준 삼으면 안 된다. 책은 원본이 바뀔 때만 다시 서므로, 장이
   *   끝나 메신저가 조용해지면 T 가 그 시각에 붙박인다 — 초록불이 켜진 채로
   *   15분 전 시각을 보여 주게 된다(2026-09-04 실측: 옛 화면 17:29:29 대
   *   새 화면 17:13:39).
   * ★첫 하트비트는 최대 15초 뒤에 오니, 그때까지는 책의 T 로 시작한다.
   */
  const anchor = useRef<{ s: number; at: number } | null>(null);
  const T = ref?.T;
  useEffect(() => {
    if (T != null && !anchor.current) anchor.current = { s: T, at: Date.now() };
  }, [T]);
  useEffect(() => {
    const tick = () => {
      const a = anchor.current;
      if (!a) return;
      const s = a.s + Math.floor((Date.now() - a.at) / 1000);
      setClock(`${p2(Math.floor(s / 3600) % 24)}:${p2(Math.floor((s % 3600) / 60))}:${p2(s % 60)}`);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  /* 관심 종목 알림. 켠 뒤에 «새로» 들어온 행만 본다 — 켜는 순간 하루치가
     한꺼번에 울리면 안 된다. 권한이 없으면 조용히 아무것도 안 한다. */
  useEffect(() => {
    if (!alarm || !rows.length) return;
    const last = rows[rows.length - 1].i;
    if (!seen.current) {
      seen.current = last;
      return;
    }
    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
    for (const e of rows) {
      if (e.i <= seen.current) continue;
      const k = watchKey(e);
      if (!k || !watch.has(k)) continue;
      try {
        new Notification(`${e.n ?? k} ${e.s === 'S' ? '매도' : e.s === 'B' ? '매수' : ''}`, {
          body: e.raw ?? '',
          tag: `kbond-${k}`,
        });
      } catch {
        /* 알림이 막혀 있어도 화면은 돈다 */
      }
    }
    seen.current = last;
  }, [rows, alarm, watch]);

  /* SSE — 책이 바뀔 때만 온다. 15초 조용하면 «끊김» 으로 본다(하트비트가 있다). */
  useEffect(() => {
    if (conn === 'setup' || conn === 'booting') return;
    const es = new EventSource(url('/events'));
    es.onmessage = (ev) => {
      lastBeat.current = Date.now();
      setConn('live');
      try {
        const snap = JSON.parse(ev.data) as { feed?: FeedRow[]; n_msg?: number };
        if (snap.n_msg) setNMsg(snap.n_msg);
        const f = snap.feed ?? [];
        setRows((prev) => {
          const next = prev.slice();
          for (const e of f) {
            if (e.i > maxI.current) {
              next.push(e);
              maxI.current = e.i;
            }
          }
          return next.length > 6000 ? next.slice(-6000) : next;
        });
      } catch {
        /* 한 프레임이 깨져도 다음 프레임이 온다 */
      }
    };
    es.addEventListener('hb', (ev) => {
      lastBeat.current = Date.now();
      /* 하트비트는 서버의 «지금» 을 싣는다 — 시계를 여기에 다시 건다. */
      try {
        const { now } = JSON.parse((ev as MessageEvent).data) as { now?: string };
        if (now) {
          const [hh, mm, ss] = now.split(':').map(Number);
          if (Number.isFinite(hh) && Number.isFinite(mm) && Number.isFinite(ss)) {
            anchor.current = { s: hh * 3600 + mm * 60 + ss, at: Date.now() };
          }
        }
      } catch {
        /* 한 박자 깨져도 다음 하트비트가 온다 */
      }
    });
    es.onerror = () => es.close();
    const tick = setInterval(() => {
      if (lastBeat.current && Date.now() - lastBeat.current > 15000) setConn('stale');
    }, 3000);
    return () => {
      es.close();
      clearInterval(tick);
    };
  }, [conn === 'setup' || conn === 'booting']); // eslint-disable-line react-hooks/exhaustive-deps

  if (conn === 'setup') {
    return (
      <Setup
        defaultBase={apiBase() || DEFAULT_API}
        onDone={(b, t) => {
          setApi(b, t);
          location.reload();
        }}
      />
    );
  }

  const counts: Record<string, number> = ref?.counts ?? {};
  const filtFn = FILTS.find(([k]) => k === filt)?.[2] ?? (() => true);
  const shown = rows.filter((e) => filtFn(e.k));

  return (
    <div className="kb-app">
      <HStack className="kb-bar" alignItems="center" gap={2}>
        <Text as="span" font="headline">
          K-Bond
        </Text>
        <div className="kb-seg">
          {TABS.map(([k, label, ck]) => (
            <button key={k} className={tab === k ? 'on' : undefined} onClick={() => setTab(k)}>
              {label}
              {counts[ck] ? <span className="c">{counts[ck].toLocaleString()}</span> : null}
            </button>
          ))}
        </div>
        <Box flexGrow={1} />
        <Text as="span" font="legal" color="fgMuted">
          {nMsg ? `오늘 ${nMsg.toLocaleString()}건` : ''}
        </Text>
        <button
          className={`kb-bell${alarm ? ' on' : ''}`}
          title="관심 종목 알림 — 브라우저 알림도 켭니다"
          onClick={async () => {
            if (!alarm && typeof Notification !== 'undefined' && Notification.permission === 'default') {
              try {
                await Notification.requestPermission();
              } catch {
                /* 거절해도 별표는 남는다 */
              }
            }
            seen.current = 0;
            setAlarm((v) => !v);
          }}
        >
          🔔 알림{watch.size ? ` ${watch.size}` : ''}
        </button>
        <span className={`kb-dot${conn === 'live' ? ' on' : ''}`} />
        <Text as="span" font="label2">
          {conn === 'live' ? '실시간' : '끊김'}
        </Text>
        <span className="kb-clock">{clock || '--:--:--'}</span>
        <Button variant="secondary" size="xs" onClick={() => setConn('setup')}>
          설정
        </Button>
      </HStack>

      {tab === 'main' ? (
        <div className="kb-main">
          <div className="kb-card kb-mainfeed">
            <div className="kb-ch">
              <Text as="span" font="label2">
                K-Bond
              </Text>
              <Text as="span" font="legal" color="fgMuted">
                블커본드 · 막무가내 통합
              </Text>
              <Text as="span" font="legal" color="fgMuted">
                {shown.length.toLocaleString()}건 (최근 {rows.length.toLocaleString()}줄)
              </Text>
            </div>
            <div className="kb-filt">
              {FILTS.map(([k, label, ok]) => (
                <button
                  key={k}
                  className={filt === k ? 'on' : undefined}
                  onClick={() => setFilt(k)}
                >
                  {label}
                  <span className="c">{rows.filter((e) => ok(e.k)).length.toLocaleString()}</span>
                </button>
              ))}
            </div>
            <Feed rows={shown} />
          </div>
          <div className="kb-card kb-mainheat">
            <div className="kb-ch">
              <Text as="span" font="label2">
                전일 민평 대비
              </Text>
              <Text as="span" font="legal" color="fgMuted">
                테너별 · bp
              </Text>
            </div>
            {ref?.heat ? <Heat heat={ref.heat} /> : <div className="kb-empty">부르는 중…</div>}
          </div>
        </div>
      ) : tab === 'dyn' ? (
        <Trends ttl={ttl} onTtl={setTtl} />
      ) : tab === 'cr' ? (
        <Credit ttl={ttl} onTtl={setTtl} feed={rows} />
      ) : (
        <Bonds lane={tab} ttl={ttl} onTtl={setTtl} feed={rows} />
      )}

      {/* 옛 화면 하단 캡션 — 문구를 그대로 옮겼다(읽는 법을 화면이 스스로 말한다). */}
      <div className="kb-foot">
        블커본드·막무가내 두 방을 파싱해 그대로 흘립니다 · 종류: 호가·체결·문의(관심 포함)·미해석 ·
        값이 안 붙은 행은 아직 못 읽은 것입니다(교체 다리, «원» 단위 크레딧 호가 등) ·
        수량 기본단위 100억, 100억 미만은 자투리 · 전일민평 = 국고·통안은 DB 전일 민평(통안 최신물은
        적재가 며칠 늦어 «전일» 이 아닐 수 있습니다), 크레딧·국주·MBS 는 문면에 적힌 민평 ·
        할인조정 = 그 민평에 오바/언더·«원» 호가를 얹어 복원한 값, «민» 표식은 문면에 레벨이 없어
        민평 그 자리라는 뜻입니다 · 브로커 = 딜러(K###) · 회사명 = 하우스(H##), 둘 다 가림 라벨입니다
      </div>
    </div>
  );
}
