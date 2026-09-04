'use client';

/** 메시지 한 줄. 파싱 결과를 원문과 나란히 보인다 — «값이 안 붙은 행» 이 보이는 것이
 *  이 화면의 요점이다(아직 못 읽은 것을 숨기지 않는다). */
import { memo, useEffect, useRef } from 'react';

import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
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

const Row = memo(function Row({ e, on, onStar }: {
  e: FeedRow;
  on: boolean;
  onStar: (k?: string | null) => void;
}) {
  const [kn, kc] = KIND[e.k ?? 'OTHER'] ?? ['기타', ''];
  const wk = watchKey(e);
  return (
    <VStack className="kb-row" paddingY={1}>
      <HStack alignItems="baseline" gap={2}>
        <Text as="span" font="legal" color="fgMuted">
          {hms(e.t)}
        </Text>
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
        <Box
          paddingX={1}
          background={kc === 'q' ? 'bgPrimaryWash' : kc === 'c' ? 'bgSecondary' : 'bgAlternate'}
        >
          <Text as="span" font="legal">
            {kn}
          </Text>
        </Box>
        {e.s ? (
          <Text as="span" font="legal" className={e.s === 'S' ? 'sr-down' : 'sr-up'}>
            {e.s === 'S' ? '매도' : '매수'}
          </Text>
        ) : null}
        <Text as="span" font="label2">
          {e.n ?? ''}
        </Text>
        {e.y != null ? (
          <Text as="span" font="headline">
            {n3(e.y)}
          </Text>
        ) : null}
        {e.a ? (
          <Text as="span" font="legal" color="fgMuted">
            {lot(e.a)}
          </Text>
        ) : null}
        <Box flexGrow={1} />
        <Text as="span" font="legal" color="fgMuted">
          {e.d ?? ''}
        </Text>
      </HStack>
      <Text as="span" font="legal" color="fgMuted">
        {e.raw ?? ''}
      </Text>
    </VStack>
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
