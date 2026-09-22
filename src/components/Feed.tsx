'use client';

/** 메시지 한 줄 — 한 행이 곧 한 줄인 표.
 *
 * [OWNER 2026-09-22] 「문장 형태가 아니라 그냥 시간, 종목명, 매수/매도, 브로커,
 *   회사명, 어제자 해당 종목 민평, 할인조정가격, 원문 이런식으로 표로」
 * [OWNER 2026-09-22 오후] 「원문을 그냥 밑에 2단으로 두지 말고, 수량 옆에 붙여버려」
 *   — 아침의 «아래 줄» 결정을 뒤집는다. 원문이 칸이 되면 긴 줄은 잘리지만(남는 폭을
 *   전부 줘도 60자쯤에서 끊긴다) 한 행이 한 줄이 되어 같은 화면에 두 배가 들어온다.
 *   잘린 줄은 마우스를 올리면 전체가 뜬다(`title`).
 *
 * ★칸 폭은 `kbond.css` 의 `--kb-cols` 한 곳에서만 정한다. 머리글(`.kb-fhead`)과
 *   행(`.kb-row`)이 같은 변수를 읽으므로 둘이 갈라질 수 없다. `<table>` 의 내용
 *   기반 자동 폭은 쓰지 않는다 — 새 줄이 흐를 때마다 칸 폭이 흔들려 읽던 자리를
 *   잃는다.
 * ★머리글은 스크롤 상자 «안» 에 sticky 로 둔다. 밖에 두면 세로 스크롤바 폭만큼
 *   칸이 어긋난다(같은 padding 을 줘도 그렇다).
 * ★«값이 안 붙은 행» 은 그대로 흘린다 — 칸이 비어 있는 것이 곧 «아직 못 읽었다»
 *   는 뜻이고, 그게 이 화면의 요점이다. 숨기지 않는다.
 */
import { memo, useEffect, useRef } from 'react';

import { Text } from '@coinbase/cds-web/typography';

import type { FeedRow } from '@/lib/api';
import { useWatch, watchKey } from '@/lib/watch';

const KIND: Record<string, [string, string]> = {
  QUOTE: ['호가', 'q'],
  CONFIRM: ['체결', 'c'],
  AXE: ['관심', 'i'],
  INQUIRY: ['문의', 'i'],
  THANKS: ['인사', ''],
  OTHER: ['미해석', ''],
  /* ★2026-09-04 P5·P6 로 새로 생긴 유형. 호가 흐름이 아니라 «말» 이다. */
  NOTICE: ['공고', ''],
  EVAL: ['평가', ''],
  STATE: ['상태', ''],
};

const p2 = (n: number) => String(n).padStart(2, '0');
const hms = (t: number) =>
  `${p2(Math.floor(t / 3600))}:${p2(Math.floor((t % 3600) / 60))}:${p2(t % 60)}`;
const n3 = (v?: number | null) => (v == null ? '' : v.toFixed(3));
/** 수량 기본단위 100억 [OWNER] — «1계약» 이 아니라 «100억» 으로 적어야 합산이 된다. */
const lot = (a?: number | null) => (a == null || !a ? '' : `${Math.round(a * 10) / 10}억`);

/** 머리글 — 행(`.kb-row`)과 같은 격자를 쓴다. 둘째 칸(☆)은 이름이 없다. */
function Head() {
  return (
    <div className="kb-fhead">
      <span>시간</span>
      <span />
      <span>종류</span>
      <span>종목명</span>
      <span>매매</span>
      <span>브로커</span>
      <span>회사명</span>
      <span className="num">전일민평</span>
      <span className="num">할인조정</span>
      <span className="num">수량</span>
      <span>원문</span>
    </div>
  );
}

const Row = memo(function Row({ e, on, onStar }: {
  e: FeedRow;
  on: boolean;
  onStar: (k?: string | null) => void;
}) {
  const [kn, kc] = KIND[e.k ?? 'OTHER'] ?? ['기타', ''];
  const wk = watchKey(e);
  return (
    <div className="kb-row">
      <span className="kb-c t">{hms(e.t)}</span>
      {/* 관심 종목 — 옛 화면의 ☆ 자리. 종목이 없는 행에는 별을 달지 않는다. */}
      {wk ? (
        <button
          className={`kb-star${on ? ' on' : ''}`}
          title="관심 종목"
          onClick={() => onStar(wk)}
        >
          {on ? '★' : '☆'}
        </button>
      ) : (
        <span className="kb-star ph" />
      )}
      <span className={`kb-kd${kc ? ` ${kc}` : ''}`}>{kn}</span>
      <span className="kb-c n" title={e.n ?? undefined}>
        {e.n ?? ''}
      </span>
      <span className={`kb-c s${e.s === 'S' ? ' sr-down' : e.s === 'B' ? ' sr-up' : ''}`}>
        {e.s === 'S' ? '매도' : e.s === 'B' ? '매수' : ''}
      </span>
      {/* 브로커 = 사람 이름(메신저 대화명) · 회사명 = 데스크 «유진증권 CM팀»
          [OWNER 2026-09-22 「브로커는 브로커 이름이 나오게하고, 회사면은 지금 브로커에
          들어가는 그 팀이 들어가게」].
          ★`bk`(딜러 키)는 안 쓴다 — 서버에서 «전화 한 줄» 을 정규화한 값이라 가림을
            끄면 칸에 전화번호가 뜬다. 하우스 축약(`h`, «유진»)은 데스크 이름이 이미
            회사를 품고 있어 칸을 따로 안 준다(툴팁에만 남긴다). */}
      <span className="kb-c who" title={e.p ?? undefined}>
        {e.p ?? ''}
      </span>
      <span className="kb-c h" title={e.h ? `${e.d ?? ''} · ${e.h}` : (e.d ?? undefined)}>
        {e.d ?? ''}
      </span>
      <span className="kb-c num">{n3(e.mp)}</span>
      {/* 할인조정가격 = 민평에 오바/언더·원 호가를 얹어 복원한 값(서버가 낸다).
          ★`atmp` 는 «문면에 레벨이 없고 민평 그 자리» 라는 뜻이라 민평과 값이 같다.
            표식이 없으면 같은 숫자 둘이 배관 오류처럼 보인다. */}
      <span className="kb-c num y">
        {n3(e.y)}
        {e.y != null && e.atmp ? (
          <i className="kb-atmp" title="문면에 레벨이 없다 — 민평 그 자리">
            민
          </i>
        ) : null}
      </span>
      <span className="kb-c num a">{lot(e.a)}</span>
      {/* 원문 — 마지막 칸이고 남는 폭을 전부 먹는다 [OWNER 2026-09-22 오후].
          ★`title` 은 여기서 장식이 아니다. 이 칸이 잘리면 칸값을 검산할 길이 없어지고,
            검산이 이 화면의 요점이다(값이 안 붙은 행을 숨기지 않는 것과 같은 이유). */}
      <span className="kb-c raw" title={e.raw ?? undefined}>
        {e.raw ?? ''}
      </span>
    </div>
  );
});

export function Feed({ rows }: { rows: FeedRow[] }) {
  const box = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const { watch, toggle } = useWatch();

  /** 맨 아래에 있었으면 새 줄을 따라가고, 위로 올려 읽는 중이면 그대로 둔다.
   *  ★전면 재구축이 스크롤을 날리는 문제는 v1 HTML 에서 이미 겪었다. */
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    if (stick.current) el.scrollTop = el.scrollHeight;
  }, [rows]);

  const onScroll = () => {
    const el = box.current;
    if (!el) return;
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
  };

  const shown = rows.slice(-800);
  return (
    <div ref={box} onScroll={onScroll} className="kb-feed">
      <Head />
      {shown.length ? (
        shown.map((e) => (
          <Row key={e.i} e={e} on={watch.has(watchKey(e) ?? '')} onStar={toggle} />
        ))
      ) : (
        <Text as="p" font="body" color="fgMuted">
          메시지를 기다리는 중입니다.
        </Text>
      )}
    </div>
  );
}
