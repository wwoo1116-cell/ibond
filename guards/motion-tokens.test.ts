import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { EASE_OUT, MOTION } from '@/theme/motion';
import { stripComments } from './_source';

/**
 * 시간은 한 곳에 산다 — 그리고 그 한 곳이 **두 파일**이라서 이 가드가 있다.
 *
 * `theme/motion.css` 가 CSS 쪽, `theme/motion.ts` 가 JS 쪽이다. 나눈 이유는 취향이
 * 아니라 기구다: 커스텀 속성은 `setTimeout` 인자나 인라인 `transition` 문자열이 될
 * 수 없다. 나눠진 값은 어긋나므로 여기서 실제로 두 파일을 읽어 대조한다.
 * (`theme/ramp.ts` 의 EDGE_OPACITY 가 다크 헤어라인과 맺은 것과 같은 관계.)
 *
 * 두 번째 일이 더 중요하다: **시간이 다른 데 또 적히는 것**을 막는다. v2 는 이
 * 가드가 생기기 전 다섯 군데에 흩어져 있었고(`type.css` 0.12s ×3,
 * `useFlipReorder.ts` 220ms + 곡선), 값이 우연히 맞았을 뿐이었다.
 */

const ROOT = path.resolve(import.meta.dirname, '..');
const CSS_FILE = path.join('src', 'theme', 'motion.css');
const TS_FILE = path.join('src', 'theme', 'motion.ts');

const EXTS = new Set(['.ts', '.tsx', '.css']);

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '.next') continue;
      walk(full, out);
    } else if (EXTS.has(path.extname(entry.name))) {
      out.push(full);
    }
  }
  return out;
}


const css = fs.readFileSync(path.join(ROOT, CSS_FILE), 'utf8');

function cssVar(name: string): string {
  // 첫 선언 = 감속 미적용 값. 두 번째는 reduced-motion 블록의 0ms 다.
  const m = new RegExp(`--${name}:\\s*([^;]+);`).exec(css);
  return m ? m[1].trim() : '';
}

describe('모션 토큰', () => {
  it('세 시간이 CSS 와 TS 에서 같다', () => {
    expect(cssVar('sr-motion-fast')).toBe(`${MOTION.fast}ms`);
    expect(cssVar('sr-motion-base')).toBe(`${MOTION.base}ms`);
    expect(cssVar('sr-motion-exit')).toBe(`${MOTION.exit}ms`);
  });

  it('곡선이 CSS 와 TS 에서 같다', () => {
    expect(cssVar('sr-ease-out')).toBe(EASE_OUT);
  });

  it('퇴장은 등장보다 짧다', () => {
    // 규칙이지 우연이 아니다 [v1 §14].
    expect(MOTION.exit).toBeLessThan(MOTION.base);
    expect(MOTION.fast).toBeLessThan(MOTION.exit);
  });

  it('감속 설정에서 토큰이 0 이 되고, 블랭킷도 함께 선다', () => {
    const reduced = /@media\s*\(prefers-reduced-motion:\s*reduce\)/.exec(css);
    expect(reduced, 'reduced-motion 블록이 없다').not.toBeNull();
    const block = css.slice(reduced!.index);
    expect(block).toMatch(/--sr-motion-fast:\s*0ms/);
    expect(block).toMatch(/--sr-motion-base:\s*0ms/);
    expect(block).toMatch(/--sr-motion-exit:\s*0ms/);
    // 저자가 잊은 자리까지 덮는 블랭킷. 이게 없으면 토큰을 안 쓴 transition 이 산다.
    expect(block).toMatch(/transition-duration:\s*0\.01ms\s*!important/);
    expect(block).toMatch(/animation-duration:\s*0\.01ms\s*!important/);
  });

  it('스타일시트가 실제로 로드된다', () => {
    const layout = fs.readFileSync(path.join(ROOT, 'src', 'app', 'layout.tsx'), 'utf8');
    // 토큰 파일이 import 되지 않으면 var() 가 전부 무효값이 되고, 화면은
    // "transition 이 없는" 상태로 조용히 산다 — 이 리포가 CSS 변수에서 세 번 밟은 얼굴.
    expect(layout).toMatch(/theme\/motion\.css/);
  });

  it('시간과 곡선이 다른 파일에 다시 적히지 않았다', () => {
    const files = walk(path.join(ROOT, 'src')).map((f) => path.relative(ROOT, f));
    const offenders: string[] = [];

    for (const rel of files) {
      if (rel === CSS_FILE || rel === TS_FILE) continue;
      const body = stripComments(fs.readFileSync(path.join(ROOT, rel), 'utf8'));
      body.split('\n').forEach((raw, i) => {
        const line = raw.trim();
        // CSS 의 지속시간 리터럴: `0.12s`, `220ms` — 단, var() 는 통과.
        const cssDur = /(transition|animation)[^;]*?\b\d*\.?\d+m?s\b/.test(line);
        // 곡선 문자열이 통째로 다시 적힌 자리.
        const bezier = /cubic-bezier\(/.test(line);
        if (cssDur || bezier) offenders.push(`${rel}:${i + 1}  ${line}`);
      });
    }

    expect(
      offenders,
      `시간·곡선은 theme/motion.{css,ts} 에만 산다:\n  ${offenders.join('\n  ')}`,
    ).toEqual([]);
  });
});
