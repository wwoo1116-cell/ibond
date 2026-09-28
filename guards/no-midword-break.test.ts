import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { stripComments } from './_source';

/**
 * 낱말 중간 줄바꿈 금지 [OWNER 2026-08-25 — "단어에서 줄바꿈 금지. 국고, 줄
 * 바꾸고 채 뭐 이딴게 비일비재하네"]. CLAUDE.md 의 같은 이름 절이 규칙 본문이다.
 *
 * 브라우저 기본(`word-break: normal`)은 한글을 음절 아무 데서나 끊는다. 영문에는
 * 없는 병이라 이 리포는 컴포넌트마다 그것을 **따로** 발견해 왔고(type.css 에만
 * 같은 수리가 여덟 곳, 2026-08-21 주석에 「인하하고」→「인 / 하하고」 실측),
 * 그러다 새로 만든 화면이 다시 그 상태로 출하됐다. 그래서 두 가지를 잰다:
 *
 *   1. 뿌리에서 한 번 끊었나 — `body { word-break: keep-all }`.
 *   2. 그걸 되돌리는 선언이 없나 — `break-all`·`anywhere` 는 낱말을 쪼갠다.
 *
 * `overflow-wrap: break-word` 는 **금지가 아니다**: 끊을 자리가 없는 긴 토큰
 * (URL·id)이 상자를 넘는 것을 막을 뿐 낱말을 쪼개지 않는다.
 */

const ROOT = path.resolve(import.meta.dirname, '..');
const SRC = path.join(ROOT, 'src');

const BANNED = [
  { name: 'word-break: break-all', re: /word-break\s*:\s*break-all/ },
  { name: 'word-break: break-word (폐기된 별칭)', re: /word-break\s*:\s*break-word/ },
  { name: 'overflow-wrap: anywhere', re: /overflow-wrap\s*:\s*anywhere/ },
  { name: 'inline wordBreak="break-all"', re: /wordBreak\s*:\s*['"]break-all['"]/ },
];

function walk(dir: string, out: string[] = []): string[] {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name === 'node_modules' || e.name === '.next') continue;
      walk(p, out);
    } else if (/\.(ts|tsx|css)$/.test(e.name)) {
      out.push(p);
    }
  }
  return out;
}

describe('낱말 중간 줄바꿈 금지', () => {
  const files = walk(SRC);

  it('잴 소스를 실제로 찾았다', () => {
    expect(files.length).toBeGreaterThan(3);
  });

  it('뿌리가 한 번 끊는다 — body { word-break: keep-all }', () => {
    const css = stripComments(fs.readFileSync(path.join(SRC, 'theme', 'type.css'), 'utf8'));
    /* `body { … }` 블록 안에 있어야 상속으로 화면 전체가 덮인다. 어느 한
       컴포넌트에만 적으면 다음 화면이 또 발견하게 된다. */
    const bodyBlocks = [...css.matchAll(/(^|\})\s*body\s*\{([^}]*)\}/g)].map((m) => m[2]);
    expect(bodyBlocks.length).toBeGreaterThan(0);
    expect(
      bodyBlocks.some((b) => /word-break\s*:\s*keep-all/.test(b)),
      'body 에 word-break: keep-all 이 없어요 — 한글이 음절 단위로 쪼개집니다.',
    ).toBe(true);
  });

  it('그 규칙을 되돌리는 선언이 없다', () => {
    const hits: string[] = [];
    for (const f of files) {
      const body = stripComments(fs.readFileSync(f, 'utf8'));
      for (const b of BANNED) {
        if (b.re.test(body)) hits.push(`${path.relative(ROOT, f)} — ${b.name}`);
      }
    }
    expect(hits, hits.join('\n')).toEqual([]);
  });
});
