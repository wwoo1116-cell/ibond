import { describe, expect, it } from 'vitest';

import { KEEP, SHOW, alarmFade, mergeAlarms } from '../src/lib/alarms';
import type { KeptAlarm } from '../src/lib/alarms';
import type { AlarmHit } from '../src/lib/api';

/**
 * 「싼 오퍼가 왔다」 배너의 규칙 — **측정이 정한 둘**.
 *
 * 왜 이 파일이 있나: 서버의 알람은 **상태가 없다**(호가의 도착 시각으로 나이를 재서
 * 「창 안에 온 것」만 낸다). 그래서 화면이 두 가지를 해야 하는데, 둘 다 틀리면
 * **조용히** 틀린다 — 화면은 멀쩡해 보이고 수도 그럴듯하다.
 *
 *   ① 쌓기 — 60초 창이면 **대부분의 순간에 0건**이다(실측). 순간값만 그리면 배너는
 *      거의 늘 비어 있고 자리를 비운 사이 온 것을 **통째로 잃는다**.
 *   ② 접기 — 같은 도착이 5초 폴에서 **최대 12번** 실려 온다(`alarm_hits` 의 열쇠
 *      주석: 「5초 폴이면 한 도착이 최대 12번 보인다」). 접지 않으면 한 번 온 것이
 *      열두 줄이 된다.
 */

function hit(over: Partial<AlarmHit> = {}): AlarmHit {
  return {
    key: 'H01|KB국민은행1-1|50000',
    n: 'KB국민은행1-1', d: 'H01', cls: '은행채', rt: 'AAA',
    ttm: 0.5, a: 100, age: 10, val: 5, med: 0, dev: 5, won: 1.48,
    adj: true, pk: '은행채 AAA ~1년', pr: 1, pn: 8, est: false,
    ...over,
  } as AlarmHit;
}

describe('쌓기 — 받은 것을 잃지 않는다', () => {
  it('새 도착은 머리에 선다', () => {
    const seen = new Set<string>();
    let kept: KeptAlarm[] = [];
    kept = mergeAlarms(kept, [hit({ key: 'a', n: 'A' })], seen, 1000);
    kept = mergeAlarms(kept, [hit({ key: 'b', n: 'B' })], seen, 2000);
    expect(kept.map((k) => k.n)).toEqual(['B', 'A']);
  });

  it('★빈 응답이 쌓인 것을 지우지 않는다', () => {
    /* 서버가 0건을 내는 것은 「없다」가 아니라 「창 안에 안 왔다」다. 지우면
       60초마다 배너가 비고, 그게 곧 「대부분의 순간에 아무것도 안 보인다」다. */
    const seen = new Set<string>();
    let kept = mergeAlarms([], [hit({ key: 'a' })], seen, 1000);
    kept = mergeAlarms(kept, [], seen, 2000);
    expect(kept).toHaveLength(1);
  });

  it('넘치면 오래된 것부터 버린다', () => {
    const seen = new Set<string>();
    let kept: KeptAlarm[] = [];
    for (let i = 0; i < KEEP + 3; i += 1) {
      kept = mergeAlarms(kept, [hit({ key: `k${i}`, n: `N${i}` })], seen, 1000 + i);
    }
    expect(kept).toHaveLength(KEEP);
    expect(kept[0].n).toBe(`N${KEEP + 2}`);              // 머리가 새것
    expect(kept.map((k) => k.n)).not.toContain('N0');    // 가장 오래된 것이 빠졌다
  });
});

describe('접기 — 한 도착은 한 번', () => {
  it('★같은 열쇠가 열두 번 와도 한 줄이다', () => {
    /* 5초 폴 · 60초 창이면 한 도착이 최대 12번 보인다(서버 주석의 그 수). */
    const seen = new Set<string>();
    let kept: KeptAlarm[] = [];
    for (let i = 0; i < 12; i += 1) {
      kept = mergeAlarms(kept, [hit({ key: 'same' })], seen, 1000 + i * 5000);
    }
    expect(kept).toHaveLength(1);
  });

  it('이미 본 것이 다시 오면 시계를 다시 세지 않는다', () => {
    /* 바램은 «언제 처음 봤나» 로 잰다 — 다시 올 때마다 갱신하면 창 안에 있는 동안
       영원히 새것으로 보이고, 1분 벼랑이 화면에서 사라진다. */
    const seen = new Set<string>();
    let kept = mergeAlarms([], [hit({ key: 'same' })], seen, 1000);
    kept = mergeAlarms(kept, [hit({ key: 'same' })], seen, 60_000);
    expect(kept[0].seenAt).toBe(1000);
  });

  it('열쇠가 다르면 다른 도착이다 — 같은 종목이어도', () => {
    /* 같은 딜러가 **더 싸게** 다시 부르면 그건 새 사건이고, 도착 시각이 달라
       열쇠가 달라진다(`딜러|종목|도착초`). */
    const seen = new Set<string>();
    let kept = mergeAlarms([], [hit({ key: 'H01|X|100' })], seen, 1000);
    kept = mergeAlarms(kept, [hit({ key: 'H01|X|160' })], seen, 2000);
    expect(kept).toHaveLength(2);
  });
});

describe('바램 — 눈금은 1분 벼랑이다', () => {
  it('60초까지는 신선하다', () => {
    expect(alarmFade(0)).toBe('');
    expect(alarmFade(60)).toBe('');
  });

  it('1~5분은 한 단계, 그 뒤는 두 단계', () => {
    /* 근거: 최우선 호가 나이별 그 레벨 체결률 ~1분 90.6% → 1~5분 61.2% → 29.6%
       (국고 전 이력 35,654건). 눈금을 바꾸면 화면이 다른 사실을 말한다. */
    expect(alarmFade(61)).toBe('ag1');
    expect(alarmFade(300)).toBe('ag1');
    expect(alarmFade(301)).toBe('ag2');
  });
});

describe('한 줄을 넘기지 않는다', () => {
  it('보이는 수는 쌓는 수보다 적다 — 나머지는 「+n」이 말한다', () => {
    expect(SHOW).toBeLessThan(KEEP);
  });
});
