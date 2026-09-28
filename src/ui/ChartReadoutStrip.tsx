'use client';

/* 그림 **위**에 고정으로 서서 커서 밑의 값을 읽는 한 줄 [OWNER 2026-09-21].
 *
 * ── 왜 떠 있는 카드를 걷었나 ───────────────────────────────────────────────
 * 종전의 `ReadoutCard` 는 그림 안에 `position: absolute` 로 떠서 커서를
 * 따라다녔다. 트레이더 보고: **카드가 그림을 가린다.** 실측으로도 그 편이
 * 맞다 — 카드는 세로 약 220px 인데 오버뷰 열의 그림은 200px, 백테스트 아래
 * 차트는 140px 이라 «그림보다 큰 툴팁» 이었고, 최근 날짜를 짚을수록 가장
 * 중요한 구간을 덮었다.
 *
 * 가리지 않게 하는 방법은 자리를 더 잘 잡는 것이 아니라 **그림 밖으로 내보내는
 * 것**이다. 자리를 잡는 쪽으로 가면 카드가 커서를 피해 다니고, 피해 다니는
 * 것은 읽는 동안 글자가 움직인다는 뜻이다.
 *
 * ── 그래서 이 줄은 **안 움직인다** ─────────────────────────────────────────
 * 자리도 높이도 칸 폭도 고정이다. 커서를 움직이면 **글자만** 바뀐다. 커서가
 * 그림 밖이면 마지막 봉을 읽는다 — «비어 있는 상태» 가 없다는 뜻이고, 그래서
 * 줄이 생겼다 사라지며 그림 높이를 흔드는 일이 없다.
 *
 * ── 범례를 흡수한다 [OWNER 2026-09-21] ─────────────────────────────────────
 * 종전에는 그림 아래에 «누를 수 있는 범례»(CD·기준금리·MA 칩)가 따로 한 줄
 * 있었다. 그 범례가 존재하는 이유로 적혀 있던 문장이 «지금 그려진 것과 끄는
 * 손잡이가 한 자리에 있으면 둘이 갈릴 수가 없다» 인데, **값**은 그 자리에
 * 없었다. 셋을 한 칸에 모은다: 견본(그려진 색) · 이름(끄는 손잡이) · 값.
 * 아래 한 줄이 빠지므로 그림이 스트립에 내준 높이를 도로 받는다.
 *
 * ── CDS 부품 ───────────────────────────────────────────────────────────────
 * `HStack`/`Box`(layout) · `Text font="label2"`(typography) · `Pressable`
 * (system, 누를 수 있는 칸). CDS `Legend`(visualizations/chart)는 **못 쓴다** —
 * `useCartesianChartContext()` 를 부르는데(`Legend.js:36`) 그 컨텍스트는 CDS
 * `CartesianChart` 안에만 있고 이 앱의 차트는 `lightweight-charts` 다.
 */

import { Box, HStack } from '@coinbase/cds-web/layout';
import { Pressable } from '@coinbase/cds-web/system';
import { Text } from '@coinbase/cds-web/typography';

import { directionClass, directionGlyph, unsignedDelta } from '@/lib/tint';

/** 줄의 높이. **상수여야 한다** — `fill` 로 그리는 화면이 그림 높이를 «남는
 *  만큼» 으로 재기 때문에, 이 값이 흔들리면 그림도 같이 흔들린다
 *  (`ui/BottomStrip.tsx::STRIP_H` 가 같은 이유로 상수다). */
export const READOUT_STRIP_H = 22;

/**
 * 한 칸. 이름 옆에 값이 오고, 그려진 선이 있으면 그 색 견본이 앞에 선다.
 *
 * `chars` 는 **값이 들어갈 자리를 미리 비워 두는 수**다. 서식이 고정 자릿수라
 * (`fmtLevel`: `%` 4자리) 같은 계열의 값은 정수부만큼만 길이가 다르고, 그
 * 최대치는 **보이는 구간의 고·저를 같은 서식에 통과시키면** 나온다. 호출부가
 * 그걸 재서 준다(`slotChars`). 이게 없으면 3.9950 → 12.0100 으로 짚는 순간
 * 오른쪽 칸들이 한 글자씩 밀린다.
 */
export type StripSlot = {
  key: string;
  label: string;
  value: string;
  /** 그려진 선의 색. 없으면 견본 없이 이름만(날짜·당일 변화가 그렇다). */
  color?: string;
  /** 견본의 잉크 — 선의 무게 사다리를 그대로 든다. */
  opacity?: number;
  /** 값이 차지할 글자 수. `slotChars` 로 잰다. */
  chars?: number;
  /** 누를 수 있는 칸인가. 주면 칸 전체가 그 계열의 토글이 된다. */
  toggle?: { on: boolean; onToggle: () => void };
  /**
   * 좁아질 때 **값을 먼저 내려놓는 순서**. 큰 수가 먼저 내려간다.
   * 안 주면 어떤 폭에서도 값이 남는다(레벨).
   *
   * 내려놓는 것은 **값뿐이고 견본과 이름은 남는다** [OWNER 2026-09-21] —
   * 이 줄이 범례이기도 해서, 칸을 통째로 떨구면 좁은 창에서 그 계열을 켜고
   * 끌 길이 없어진다. 잊는 것은 숫자뿐이고 그건 창을 키우면 돌아온다.
   *
   * 여섯 단인 이유는 실측이다 [2026-09-21 브라우저]: MA 를 다섯 다 켜면
   * 떨굴 수 있는 칸이 일곱(MA 다섯 + 기준선 둘)이라 네 단으로는 모자랐다.
   */
  drop?: 1 | 2 | 3 | 4 | 5 | 6;
};

/** 값이 들어갈 자리를 **보이는 구간의 극단**으로 잰다 — 손으로 센 수가 아니다. */
export function slotChars(fmt: (v: number) => string, ...bounds: (number | null | undefined)[]) {
  let n = 1;
  for (const b of bounds) {
    if (b == null) continue;
    n = Math.max(n, fmt(b).length);
  }
  return n;
}

function SlotBody({ s }: { s: StripSlot }) {
  return (
    <>
      {s.color ? (
        /* 견본은 **그려진 선 그대로**다 — 아래 범례가 지던 그 규칙이고, 부품도
           그때 쓰던 `.sr-casedash` 그대로다(같은 모양을 손으로 다시 만들지
           않는다). 끈 계열은 흐려져 «있지만 지금은 안 그린다» 가 읽힌다. */
        <span
          className="sr-casedash"
          style={{
            background: s.color,
            opacity: s.toggle && !s.toggle.on ? 0.3 : (s.opacity ?? 1),
          }}
        />
      ) : null}
      <Text as="span" font="label2" color="fgMuted" noWrap>
        {s.label}
      </Text>
      <Text as="span" font="label2" tabularNumbers noWrap className="sr-strip-v">
        {s.value}
      </Text>
    </>
  );
}

/**
 * 한 줄 리드아웃. **그림 밖**에 서고, 커서가 없으면 마지막 봉을 읽는다.
 *
 * `change` 를 따로 받는 이유는 뜻이다 — 위의 칸들은 축에서 읽은 **레벨**이고
 * 이것은 **변화**다. 카드 시절에도 색을 가지는 줄은 이것 하나뿐이었고 그
 * 규칙은 그대로 산다(레벨은 방향이 없으므로 잉크다).
 */
export function ChartReadoutStrip({
  date,
  slots,
  change,
  ariaLabel,
}: {
  date: string;
  slots: readonly StripSlot[];
  /** 부호 있는 변화 — 이미 단위까지 붙은 글자와, 색·화살표를 고를 원래 수. */
  change?: { label: string; text: string; v: number | null };
  ariaLabel?: string;
}) {
  return (
    <HStack
      className="sr-readout-strip"
      alignItems="center"
      gap={1.5}
      paddingX={2}
      height={READOUT_STRIP_H}
      flexShrink={0}
      /* 낭독은 차트가 이미 `aria-live` 로 진다(`TimeChart.hoverLabel`). 이 줄은
         그 문장의 **눈으로 읽는 판**이라 두 번 읽히면 안 된다. */
      aria-hidden="true"
      aria-label={ariaLabel}
    >
      <Text as="span" font="label2" tabularNumbers noWrap>
        {date}
      </Text>
      {/* ── 가운데만 줄어든다 ────────────────────────────────────────────────
          **실측에서 나온 구조다** [2026-09-21 브라우저]: MA 다섯을 다 켠 화면에서
          칸이 열이 되자 `당일 변화` 가 오른쪽 끝으로 밀려 잘렸다. 폭 분기점을
          더 촘촘히 잡는 것으로는 못 고친다 — 켤 수 있는 계열 수가 변수라 어떤
          분기점을 잡아도 어떤 조합에서는 넘친다.

          그래서 «항상 보인다» 를 분기점이 아니라 **구조**로 만든다: 날짜·레벨과
          당일 변화는 줄어들지 않는 자리에 두고, 계열 칸들만 `min-width: 0` 인
          가운데 영역에서 줄어든다. 분기점 사다리는 그 안에서 «값부터 지우는»
          우아한 축소를 맡고, 못 지켜도 잘리는 것은 가운데뿐이다. */}
      <Box className="sr-strip-series">
      {slots.map((s) =>
        s.toggle ? (
          <Pressable
            key={s.key}
            className="sr-strip-slot"
            data-drop={s.drop}
            style={s.chars ? { ['--sr-strip-ch' as string]: `${s.chars}ch` } : undefined}
            accessibilityLabel={`${s.label} ${s.toggle.on ? '끄기' : '켜기'}`}
            onClick={s.toggle.onToggle}
            noScaleOnPress
            /* 바탕·테두리·활자는 `.sr-strip-slot` 이 지운다 — `Pressable` 은
               `button` 이라 UA 기본이 붙고, 그걸 style prop 으로 지우려면
               `background="transparent"` 같은 **토큰 아닌 값**을 써야 한다
               (`guards/contrast.test.ts` 가 바로 그걸 잡는다). 칸 넷이 같은
               모양이어야 하므로 리셋은 한 클래스가 진다. */
          >
            <SlotBody s={s} />
          </Pressable>
        ) : (
          <Box
            key={s.key}
            className="sr-strip-slot"
            data-drop={s.drop}
            style={s.chars ? { ['--sr-strip-ch' as string]: `${s.chars}ch` } : undefined}
          >
            <SlotBody s={s} />
          </Box>
        ),
      )}
      </Box>
      {change ? (
        /* 네 부품 한 벌 — `directionClass` + `directionGlyph` + `unsignedDelta`,
           그리고 단위. 표의 변화 셀과 **같은 문법**이라 한 화면에서 같은 양이
           두 어휘로 말해지지 않는다(CLAUDE.md 캐논 «변화 셀»).
           틴트 배경만 안 쓴다: 이 줄은 셀이 아니라 글줄이고, 칸마다 배경이
           들어오면 고정 높이 한 줄이 알약 띠로 읽힌다. */
        <Box className="sr-strip-slot sr-strip-change">
          <Text as="span" font="label2" color="fgMuted" noWrap>
            {change.label}
          </Text>
          <Text
            as="span"
            font="label2"
            tabularNumbers
            noWrap
            className={`sr-strip-v ${directionClass(change.v)}`}
          >
            {directionGlyph(change.v)} {unsignedDelta(change.text)}
          </Text>
        </Box>
      ) : null}
    </HStack>
  );
}
