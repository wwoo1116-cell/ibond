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
/** 금리 표기 [2026-09-23] — ★0.25bp 자리는 넷째 자리까지 적는다.
 *  세트호가(두 다리의 중간값)가 서는 자리라 셋째 자리로 뭉개면 «세트라는 사실»
 *  자체가 화면에서 사라진다: 3.9975 -> 3.998 은 그냥 다른 호가로 읽힌다.
 *  0.5bp 격자 값은 지금처럼 세 자리다(3.405). */
const n3 = (v?: number | null) => {
  if (v == null) return '';
  const q = Math.round(v * 10000);
  return q % 10 === 0 ? v.toFixed(3) : v.toFixed(4);
};
/** 수량 기본단위 100억 [OWNER] — «1계약» 이 아니라 «100억» 으로 적어야 합산이 된다. */
const lot = (a?: number | null) => (a == null || !a ? '' : `${Math.round(a * 10) / 10}억`);

/** 잔존 [2026-09-23] — ★1년 안쪽은 «일» 로 적는다.
 *  0.2년 이라고 적으면 만기가 코앞인 것이 안 보인다. 그 구간은 하루가 곧 값이다
 *  (잔존 78일이면 1원이 4.7bp 다 — 같은 1원이 30년물에선 0.06bp). */
const ttmTxt = (t?: number | null) => {
  if (t == null) return '';
  if (t < 0) return '만기';
  return t < 1 ? `${Math.round(t * 365)}일` : `${t.toFixed(1)}년`;
};

/** 머리글 — 행(`.kb-row`)과 같은 격자를 쓴다. 둘째 칸(☆)은 이름이 없다. */
function Head() {
  return (
    <div className="kb-fhead">
      <span>시간</span>
      <span />
      <span>종류</span>
      <span>종목명</span>
      <span className="num">만기일</span>
      <span className="num">잔존</span>
      <span>매매</span>
      <span>브로커</span>
      <span>회사명</span>
      <span className="num">전일민평</span>
      <span className="num">할인조정</span>
      {/* ★«어느 결제일인지» 를 머리글에 적는다 [2026-09-23]. 안 적으면 이 숫자는
          읽는 사람마다 달라진다 — 국고16-8 이 당일 10006.54 · 익일 10010.90 이다. */}
      <span className="num" title="액면 10,000원당 단가 · 당일결제(T) 기준">단가(T)</span>
      <span className="num">수량</span>
      <span>원문</span>
      <span className="ctr" title="이 행의 단가를 믿어도 되나 — X 는 마우스를 올리면 이유가 뜬다">검산</span>
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
      {/* 만기일·잔존 [OWNER 2026-09-23]. ★호가의 속성이 아니라 «종목» 의 속성이라
          값(할인조정)이 없는 행에도 선다 — AXE·문의에서도 「뭐가 언제 만기인지」는
          알 수 있어야 한다. 앞 넷(연도)은 잘라 적는다: 2031-03-10 → 31-03-10. */}
      <span className="kb-c num mat" title={e.mat ?? undefined}>
        {e.mat ? e.mat.slice(2) : ''}
      </span>
      <span className="kb-c num ttm" title={e.mat ? `${e.ttm}년` : undefined}>
        {ttmTxt(e.ttm)}
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
      {/* 단가 — 액면 1만원당, 당일결제(T). 제원이 없는 종목(크레딧·물가채·STRIPS)은
          서버가 비워 보낸다. ★빈칸은 «0원» 이 아니라 «못 잰다» 는 뜻이다 —
          지어내지 않고 비우는 것이 이 레인의 규약이다.
          툴팁에 수정가액(민평 대비 원)을 같이 준다 — 칸을 하나 더 늘리지 않으려고. */}
      <span
        className={`kb-c num px${e.pxa ? ' asm' : ''}`}
        title={
          e.px == null
            ? '제원이 없어 단가를 못 만든다 (크레딧·물가채·분리채)'
            : `단가 ${e.px} (결제 ${e.pxs ?? 'T'})${
                e.won != null ? ` · 수정가액 ${e.won > 0 ? '+' : ''}${e.won}원` : ''
              }${e.pxb === 'mp' ? ' · 값이 없어 전일 민평으로 냄' : ''}${
                e.pxa ? ' · 쿠폰 없이 분기복리 할인 — 잠정 규약' : ''
              }`
        }
      >
        {e.px == null ? '' : e.px.toFixed(2)}
      </span>
      <span className="kb-c num a">{lot(e.a)}</span>
      {/* 원문 — 남는 폭을 전부 먹는다 [OWNER 2026-09-22 오후].
          ★`title` 은 여기서 장식이 아니다. 이 칸이 잘리면 칸값을 검산할 길이 없어지고,
            검산이 이 화면의 요점이다(값이 안 붙은 행을 숨기지 않는 것과 같은 이유). */}
      <span className="kb-c raw" title={e.raw ?? undefined}>
        {e.raw ?? ''}
      </span>
      {/* 검산 — 원문 «뒤» [OWNER 2026-09-23]. O = 단가·수정가액·실제 금리가 서로
          닫힌다(따로 원 계산기를 안 돌려도 된다). X = 어긋난다. 빈칸 = 못 잰다. */}
      <span
        className={`kb-c ctr chk${e.chk === 'O' ? ' ok' : e.chk === 'X' ? ' no' : ''}`}
        title={
          e.chk === 'O'
            ? '이 단가를 믿어도 된다 — 제원이 있고, 만기 전이고, 민평이 오늘 것이다'
            : e.chk === 'X'
              ? `믿지 말 것 — ${e.chkw ?? '이유 미상'}`
              : '잴 수 없다 (제원·민평이 없다)'
        }
      >
        {e.chk ?? ''}
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
