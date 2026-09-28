import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { stripComments, walk } from './_source';

/**
 * 숫자를 글자로 바꾸는 일은 `src/lib/format.ts` 하나가 한다.
 *
 * ── 왜 가드가 필요한가 ─────────────────────────────────────────────────────
 * 2026-09-28 에 모으기 전, 같은 이름의 도우미가 **여섯 파일에 따로** 선언돼 있었고
 * 이미 갈려 있었다: `sbp` 가 한 파일에서만 `bp` 를 문자열에 구워 `+1.5bpbp` 를 냈고,
 * 같은 잔존이 `8M` 과 `243일` 로, 같은 빈값이 `—`·`·`·`''` 셋으로 갈렸다.
 * 갈렸다는 것보다 나쁜 것은 **아무도 모른 채** 갈려 있었다는 사실이다.
 *
 * 다음 사람이 급할 때 파일 안에 `toFixed(1)` 한 줄을 적는 것은 자연스럽고, 그 한 줄이
 * 두 번째 어휘의 시작이다. 그래서 기계가 센다.
 *
 * ── 무엇을 허용하나 ────────────────────────────────────────────────────────
 * `toFixed` 가 전부 서식인 것은 아니다. **좌표**는 서식이 아니다 — SVG 경로의
 * `x.toFixed(1)` 은 사람이 읽을 숫자가 아니라 그리기 위한 수다. 그래서 «그림을 그리는
 * 파일» 은 예외로 두되, 그 목록은 **줄기만 하고 늘지 않는다**(래칫).
 */

const ROOT = path.resolve(import.meta.dirname, '..');
const SRC = path.join(ROOT, 'src');

/** 서식의 정본. 여기서는 무엇이든 해도 된다. */
const FORMAT_FILE = path.join('src', 'lib', 'format.ts');

/**
 * 좌표를 다루는 파일 — `toFixed` 가 «그리기» 에 쓰인다.
 *
 * ★래칫이다: 이 목록은 줄기만 한다. 차트를 `src/chart/*` 로 옮기면 여기서 빠진다.
 *   새 파일을 더하려면 그 파일이 왜 좌표를 직접 다루는지 여기에 적어야 한다.
 */
const COORD_FILES = new Set([
  path.join('src', 'components', 'Bonds.tsx'), // 시세 SVG 경로·눈금
  path.join('src', 'components', 'Curve.tsx'), // 잔존×YTM 산점도 좌표
  path.join('src', 'components', 'Trends.tsx'), // 맥박 막대 좌표
  path.join('src', 'components', 'Heat.tsx'), // 틴트 농도 산술
  path.join('src', 'lib', 'tint.ts'), // 알파 산술
]);

/** 서식을 손으로 짜는 신호들. */
const HAND_FORMAT = [
  { re: /\.toFixed\(/, why: 'toFixed — `lib/format` 의 함수를 쓴다' },
  { re: /\.padStart\(\s*2\s*,/, why: 'padStart(2) — 시각은 `fmtHms`/`fmtHm`' },
  { re: /\.toLocaleString\(/, why: 'toLocaleString — 천단위는 `fmtCount`' },
];

describe('서식은 한 파일이 진다', () => {
  const files = walk(SRC, ['.ts', '.tsx']).map((f) => path.relative(ROOT, f));

  it('검사할 소스를 찾는다', () => {
    expect(files.length).toBeGreaterThan(8);
  });

  it.each(files.filter((f) => f !== FORMAT_FILE))('%s 는 서식을 손으로 안 짠다', (rel) => {
    const coord = COORD_FILES.has(rel);
    const body = stripComments(fs.readFileSync(path.join(ROOT, rel), 'utf8'));
    const offenders: string[] = [];
    body.split('\n').forEach((line, i) => {
      for (const { re, why } of HAND_FORMAT) {
        // 좌표 파일에서는 `toFixed` 만 봐준다 — 시각·천단위는 좌표가 아니다.
        if (coord && re.source.includes('toFixed')) continue;
        if (re.test(line)) offenders.push(`  ${rel}:${i + 1}  ${line.trim()}   ← ${why}`);
      }
    });
    expect(offenders, `서식을 손으로 짠 자리:\n${offenders.join('\n')}`).toEqual([]);
  });

  it('도우미가 파일 안에 다시 선언되지 않는다', () => {
    // 옛 이름 그대로 부활하는 것이 가장 흔한 재발 경로다.
    const OLD_NAMES = /^\s*const\s+(n3|sbp|lot|hms|hm|p2|ttmTxt|tickTxt|ageTxt)\s*=/m;
    const hits = files
      .filter((rel) => rel !== FORMAT_FILE)
      .filter((rel) => OLD_NAMES.test(stripComments(fs.readFileSync(path.join(ROOT, rel), 'utf8'))));
    expect(hits, `서식 도우미를 다시 선언한 파일: ${hits.join(', ')}`).toEqual([]);
  });

  it('빈값 표식과 마이너스는 정본에만 박혀 있다', () => {
    const fmt = fs.readFileSync(path.join(ROOT, FORMAT_FILE), 'utf8');
    expect(fmt).toMatch(/export const EMDASH = '—'/);
    expect(fmt).toMatch(/export const MINUS = '−'/);
  });
});
