/**
 * 「싼 오퍼가 왔다」 배너의 **규칙 두 개** — 순수 함수.
 *
 * 컴포넌트에서 빼 둔 이유: 이 둘이 **측정이 정한 것**이고, 그래서 틀리면 조용히
 * 틀린다(화면은 멀쩡해 보인다). 순수 함수면 렌더러 없이 잴 수 있다.
 *
 * ★① **쌓는다** — 서버는 「창(60초) 안에 온 것」만 낸다(상태 없음). 대부분의 순간에
 *    0건이므로(실측) 순간값만 그리면 자리를 비운 사이 온 것을 통째로 잃는다.
 * ★② **`key` 로 접는다** — 같은 도착이 5초 폴에서 **최대 12번** 실려 온다
 *    (`kbond_view.alarm_hits` 의 열쇠 = `딜러|종목|도착초`). 접지 않으면 한 번 온
 *    것이 열두 줄이 된다.
 */
import type { AlarmHit } from './api';

/** 쌓인 알람 한 건 — 서버가 준 것 + 「언제 봤나」(바램을 재는 시계). */
export type KeptAlarm = AlarmHit & { seenAt: number };

/** 쌓아 두는 최대 건수. 넘치면 **오래된 것부터** 버린다. */
export const KEEP = 12;

/** 한 줄에 보이는 최대 — 나머지는 「+n」. 바 아래 한 줄을 넘기지 않으려는 값이다. */
export const SHOW = 4;

/**
 * 바램 단계 — ★눈금은 이 앱의 것과 **같은 값**이다(`AGE_STEPS` 60·300).
 *
 * 근거는 1분 벼랑이다: 최우선 호가 나이별로 그 레벨에서 체결이 난 비율이
 * ~1분 90.6% → 1~5분 61.2% → 5분+ 29.6%(국고 전 이력 35,654건).
 */
export function alarmFade(sec: number): '' | 'ag1' | 'ag2' {
  if (sec <= 60) return '';
  return sec <= 300 ? 'ag1' : 'ag2';
}

/**
 * 받은 것을 쌓는다 — **새것이 머리에**, 같은 도착은 **한 번만**, 최대 `keep` 건.
 *
 * `seen` 은 이미 본 열쇠다(부수효과로 채운다 — 폴마다 비교만 하고 렌더에 안 쓰므로
 * 상태에 두면 쓸데없는 렌더가 한 번씩 더 돈다). 이미 본 것이 다시 오면 **아무 일도
 * 안 한다** — 「다시 울림」이 아니라 「같은 도착이 아직 창 안에 있다」는 뜻이다.
 */
export function mergeAlarms(
  prev: KeptAlarm[],
  incoming: readonly AlarmHit[],
  seen: Set<string>,
  now: number,
  keep: number = KEEP,
): KeptAlarm[] {
  const fresh = incoming.filter((h) => !seen.has(h.key));
  if (!fresh.length) return prev;
  for (const h of fresh) seen.add(h.key);
  return [...fresh.map((h) => ({ ...h, seenAt: now })), ...prev].slice(0, keep);
}
