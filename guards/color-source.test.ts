import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';
import { stripComments } from './_source';

/**
 * Every colour literal in v2 lives in ONE file. A hex pasted into a component is
 * a palette fork that no contrast guard can see.
 *
 * ── Why comments are stripped and string literals are NOT — SETTLED [pass 2] ──
 * The first session prompt asked for both. Comments, yes: prose describing a
 * removed rule tripped this class of guard four times in v1, and a comment cannot
 * paint anything.
 *
 * String literals, NO. In a `.ts`/`.tsx` file a colour IS a string literal
 * (`style={{ color: '#d92d3c' }}`), so stripping them would blind the guard to
 * precisely the thing it exists to catch — leaving a test that passes by being
 * unable to look. This was Provisional; the owner accepted the reasoning and it
 * is now settled.
 *
 * **Do not "fix" this back.** A future session reading the original instruction
 * will be tempted to add string-literal stripping for consistency with the
 * prompt's letter. That change would make this file green and useless.
 */

const ROOT = path.resolve(import.meta.dirname, '..');
const TOKEN_FILE = path.join('src', 'theme', 'direction.css');

const SEARCH_DIRS = ['src', 'guards'];
const EXTS = new Set(['.ts', '.tsx', '.css', '.mjs', '.js']);

/** `#abc`, `#aabbcc`, `#aabbccdd` — but not a CSS custom property or an id selector. */
const HEX = /#[0-9a-fA-F]{3,8}\b/;
const RGB = /\brgba?\(/;

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

/** Block and line comments, in both CSS and TS. Not a parser — it does not need
 * to be: it only has to remove text that can never paint a pixel. */

describe('colour lives in one file', () => {
  const files = SEARCH_DIRS.flatMap((d) => {
    const abs = path.join(ROOT, d);
    return fs.existsSync(abs) ? walk(abs) : [];
  });

  it('finds source to check at all', () => {
    expect(files.length).toBeGreaterThan(3);
  });

  it.each(files.map((f) => path.relative(ROOT, f)))('%s has no colour literal', (rel) => {
    if (rel === TOKEN_FILE) return; // the one file allowed to hold hexes

    const body = stripComments(fs.readFileSync(path.join(ROOT, rel), 'utf8'));
    const offenders = body
      .split('\n')
      .map((line, i) => ({ line: line.trim(), n: i + 1 }))
      .filter(({ line }) => HEX.test(line) || RGB.test(line));

    expect(
      offenders,
      `colour literal outside ${TOKEN_FILE}:\n` +
        offenders.map((o) => `  ${rel}:${o.n}  ${o.line}`).join('\n'),
    ).toEqual([]);
  });

  it('the token file is where the direction pair actually is', () => {
    const css = fs.readFileSync(path.join(ROOT, TOKEN_FILE), 'utf8');
    expect(css).toMatch(/--sr-up:\s*#[0-9a-f]{6}/i);
    expect(css).toMatch(/--sr-down:\s*#[0-9a-f]{6}/i);
  });

  it('CDS positive/negative tokens are never referenced', () => {
    // CDS names green positive and red negative. Inverted for a KRW rates desk,
    // so direction never routes through them (session prompt V1.2).
    const hits = files
      .map((f) => path.relative(ROOT, f))
      .filter((rel) => {
        if (rel === TOKEN_FILE || rel.startsWith(path.join('guards', ''))) return false;
        const body = stripComments(fs.readFileSync(path.join(ROOT, rel), 'utf8'));
        return /\bfgPositive\b|\bfgNegative\b/.test(body);
      });
    expect(hits, `fgPositive/fgNegative referenced in: ${hits.join(', ')}`).toEqual([]);
  });
});
