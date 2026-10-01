'use client';

/**
 * 「싼 오퍼가 왔다」 배너 — 바 **아래** 한 줄. [OWNER 2026-09-30 → 10-01]
 *
 * ## 왜 이 모양인가 — 측정이 셋을 정했다
 *
 * ★① **쌓는다.** 서버는 「창(60초) 안에 온 것」만 낸다(상태 없음). 그래서
 *    **대부분의 순간에 0건**이다(실측) — 순간값만 그리면 배너는 거의 늘 비어 있고,
 *    자리를 비운 사이 온 것을 **통째로 잃는다**. 받은 것을 여기서 쌓는다.
 * ★② **`key` 로 접는다.** 같은 도착이 5초 폴에서 **최대 12번** 실려 온다
 *    (`kbond_view.alarm_hits` 의 그 열쇠 = `딜러|종목|도착초`). 화면이 접지 않으면
 *    한 번 온 것이 열두 줄이 된다.
 * ★③ **가벼운 자리를 쓴다.** `/api/view?lane=cr` 은 **455KB** 다(오퍼 825개).
 *    알람만 보려고 그걸 5초마다 받으면 [OWNER 2026-09-23 「렉이 미친듯이 걸림」]을
 *    다시 만든다. `/api/alarms` 는 **0.06KB** 라 어느 탭에 있어도 들을 수 있다.
 *
 * ## 배치 캐논을 안 깬다
 *
 * 바(`.kb-bar`)와 같은 `flex: none` 줄이고 **쌓인 것이 없으면 아무 자리도 안 먹는다**
 * (`null` 을 낸다). 판·페이지는 여전히 안 구른다(`kbond.css` 머리 §배치 캐논 ①②③).
 * @730 실측: 바 63 · 캡션 27 · 판 638 — 이 줄은 울렸을 때만 선다.
 *
 * ## 「알람」이 둘이다 — 이름을 가른다
 *
 * 바의 🔔 는 **관심 종목 알림**(내가 별 찍은 종목에 새 메시지가 오면 브라우저 알림)이고
 * 피드를 본다. 이것은 **「무리 중앙보다 N bp 싼 오퍼가 방금 왔다」** 이고 책을 본다.
 * 둘은 다른 물건이라 같은 낱말을 쓰지 않는다.
 *
 * ## bp 옆에 **돈**을 적는 이유
 *
 * 열린 결정 ②가 그것이다 — bp 는 짧은 잔존에서 돈이 아니다(잔존 0.01년의 3bp 는
 * 100억에 **3만원**, 1년이면 **289만원** · 1,000배). 문턱을 bp 하나로 두면 짧은 잔존이
 * 목록을 먹는다. 환산은 **서버가** 한다(`won`) — 화면이 표를 베끼면 두 벌이 된다.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { Text } from '@coinbase/cds-web/typography';

import { getAlarms } from '@/lib/api';
/* ★규칙 둘(쌓기·접기)은 `lib/alarms` 가 진다 — 측정이 정한 것이라 순수 함수로 빼
   시험이 렌더러 없이 잰다(`guards/alarms.test.ts`). 여기서 다시 적지 않는다. */
import { KEEP, SHOW, alarmFade, mergeAlarms } from '@/lib/alarms';
import type { KeptAlarm } from '@/lib/alarms';
import { EMDASH, fmtBpUnit, fmtTtm, fmtWon10b } from '@/lib/format';
import { Delta } from '@/ui/Delta';

/** 폴 간격(ms). ★서버의 창(60초)보다 **짧아야** 한다 — 길면 도착을 통째로 놓친다. */
const EVERY_MS = 5_000;

export function Alarms() {
  const [kept, setKept] = useState<KeptAlarm[]>([]);
  const [nBp, setNBp] = useState<number | null>(null);
  const [off, setOff] = useState(false);
  /** 이미 본 도착 — `key` 로 접는 자리. 상태에 안 두는 이유: 폴마다 비교만 하고
   *  렌더에 안 쓰므로, 상태에 두면 쓸데없는 렌더가 폴마다 한 번씩 더 돈다. */
  const seen = useRef<Set<string>>(new Set());

  const pull = useCallback(async () => {
    try {
      const a = await getAlarms();
      setNBp(a.alarm_n_bp);
      const now = Date.now();
      setKept((prev) => mergeAlarms(prev, a.alarms ?? [], seen.current, now, KEEP));
    } catch {
      /* 못 받아도 쌓인 것은 남는다 — 끊김은 바의 점이 말한다 */
    }
  }, []);

  useEffect(() => {
    if (off) return undefined;
    void pull();
    const id = setInterval(() => void pull(), EVERY_MS);
    return () => clearInterval(id);
  }, [off, pull]);

  /* 바램을 다시 그리게 하는 초침. 알람이 없으면 돌지 않는다. */
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!kept.length) return undefined;
    const id = setInterval(() => setTick((t) => t + 1), 1_000);
    return () => clearInterval(id);
  }, [kept.length]);

  /* ★쌓인 것이 없으면 **아무 자리도 안 먹는다** — 배치 캐논(판·페이지 안 구름). */
  if (off || !kept.length) return null;

  const now = Date.now();
  const shown = kept.slice(0, SHOW);
  const more = kept.length - shown.length;

  return (
    <div className="kb-alarms" role="status" aria-live="polite">
      <span className="kb-alarms-h" title={
        `무리(계열×등급×잔존칸) 중앙보다 ${nBp ?? EMDASH}bp 이상 싼 매도 호가가`
        + ` 60초 안에 온 것입니다. 문턱은 서버가 정합니다 — 화면이 고르지 않습니다.`
        + ` ⚠bp 는 짧은 잔존에서 돈이 아닙니다: 잔존 0.01년의 3bp 는 100억에 3만원이고`
        + ` 1년이면 289만원입니다. 그래서 옆에 «100억 살 때» 를 같이 적습니다.`
      }>
        싼 오퍼{nBp == null ? '' : ` ≥${fmtBpUnit(nBp)}`}
      </span>
      {shown.map((h) => (
        <span className={`kb-alarm ${alarmFade((now - h.seenAt) / 1000)}`} key={h.key}
          title={[
            h.d ?? '',
            h.pk && h.pn ? `${h.pk} ${h.pn}개 중 ${h.pr}위` : '',
            h.adj ? '커브반영으로 쟀습니다' : '민평대비로 쟀습니다',
            h.est ? '무리의 등급이 집계에서 온 것입니다' : '',
            h.med == null ? '' : `무리 중앙 ${fmtBpUnit(h.med)} · 이 오퍼 ${fmtBpUnit(h.val)}`,
          ].filter(Boolean).join(' · ')}
        >
          <b className="kb-alarm-n">{h.n}</b>
          <span className="kb-n">{fmtTtm(h.ttm)}</span>
          {/* ★방향색은 **캐논 부품**이 진다(`ui/Delta` — 틴트·방향클래스·화살표·
              무부호 숫자 네 부품 한 벌). 내 손으로 `--sr-up` 을 칠했다가
              `design-canon` 가드에 걸렸다: 방향색은 부호·매매·틴트에만 선다. */}
          <Delta v={h.dev} unit="bp" />
          {/* ★돈 — 열린 결정 ②가 화면에서 보이는 자리. 환산은 **서버**가 하고
              서식은 **`lib/format`** 이 한다(둘 다 두 벌로 두지 않는다). */}
          <span className="kb-n kb-alarm-won">{fmtWon10b(h.won)}</span>
          {h.est ? <b className="kb-badge">집계</b> : null}
        </span>
      ))}
      {more > 0 ? <span className="kb-n kb-alarms-more">+{more}</span> : null}
      <button className="kb-alarms-x" onClick={() => setKept([])} title="쌓인 것을 지웁니다">
        지우기
      </button>
      <button className="kb-alarms-x" onClick={() => setOff(true)}
        title="이 줄을 닫습니다 — 새로고침하면 다시 켜집니다">
        <Text as="span" font="legal">닫기</Text>
      </button>
    </div>
  );
}
