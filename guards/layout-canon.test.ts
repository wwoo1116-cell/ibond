import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { stripComments, walk } from './_source';

/**
 * 배치 캐논 「한 화면」 [OWNER 2026-09-29] — `kbond.css` 머리의 규칙 넷을 잰다.
 *
 *   ① 페이지는 스크롤하지 않는다   ② 판(board)도 스크롤하지 않는다
 *   ③ 스크롤은 «카드 몸통»(`.kb-cb`)이 한다   ④ 남는 높이는 가중치로 나눈다
 *
 * ★여기 있는 것은 **구조**만이다. 「730px 에서 안 넘친다」는 이 자로 못 잰다 —
 *   그건 글꼴·자료가 정하고, 브라우저에서 재야 한다(세션 실측). 재지 못하는 것을
 *   재는 척하는 시험은 초록으로 거짓말을 한다.
 */

const ROOT = path.resolve(import.meta.dirname, '..');
const SRC = path.join(ROOT, 'src');
const rel = (f: string) => path.relative(ROOT, f);
const read = (f: string) => fs.readFileSync(path.join(ROOT, f), 'utf8');
const CSS = () => stripComments(read(path.join('src', 'theme', 'kbond.css')));
/* ★주석을 걷고 센다 — `Feed.tsx` 의 «`.kb-cb` 가 준다» 라는 주석이 몸통
   하나로 잡혔다(카드 20 대 몸통 21). 세는 자는 «그리는 것»만 봐야 한다. */
const TSX = () => stripComments(walk(SRC, ['.tsx']).map((f) => read(rel(f))).join('\n'));

/** 선택자 하나의 선언 덩이 — 여러 규칙에 흩어져 있어도 합쳐서 본다. */
const block = (css: string, sel: string) =>
  [...css.matchAll(/([^{}]+)\{([^}]*)\}/g)]
    .filter((m) => m[1].split(',').some((one) => one.trim() === sel))
    .map((m) => m[2])
    .join(' ');

describe('배치 캐논 ①② — 페이지도 판도 스크롤하지 않는다', () => {
  it('html·body 가 넘침을 끊는다', () => {
    expect(/html,\s*body\s*\{[^}]*overflow:\s*hidden/.test(CSS())).toBe(true);
  });

  const BOARDS = ['.kb-bonds', '.kb-credit', '.kb-trends', '.kb-main'];

  it('판은 넘침을 숨기고, 한 줄로 서고, 스스로 스크롤하지 않는다', () => {
    const css = CSS();
    const bad: string[] = [];
    for (const b of BOARDS) {
      const body = block(css, b);
      if (!body) { bad.push(`${b} — 규칙이 없다`); continue; }
      if (!/overflow:\s*hidden/.test(body)) bad.push(`${b} — overflow: hidden 이 없다`);
      if (/overflow-y:\s*auto|overflow:\s*auto/.test(body)) bad.push(`${b} — 판이 스크롤한다(캐논 ②)`);
      if (/align-items:\s*start/.test(body)) bad.push(`${b} — align-items: start 는 열을 «내용 높이» 로 세운다`);
      if (!/grid-template-rows:\s*minmax\(0,\s*1fr\)/.test(body)) bad.push(`${b} — 행이 auto 라 내용이 높이를 정한다`);
    }
    expect(bad, `판이 캐논을 벗어났다 — ${bad.join(' | ')}`).toEqual([]);
  });

  it('고정 vh·px 캡을 쓰지 않는다', () => {
    /* 종전 `.kb-scroll { max-height: 58vh }` 가 1100px 화면에서 638px 을 물었고,
       그 열에는 962px 이 있었다 — 제 자리보다 짧게 자르면서 동시에 열을 넘치게
       했다. 높이는 부모가 주고 자식은 `min-height: 0` 으로 받는다. */
    const caps = [...CSS().matchAll(/max-height:\s*([^;]+);/g)]
      .map((m) => m[1].trim())
      .filter((v) => /\d(vh|px)/.test(v));
    expect(caps, `고정 캡: ${caps.join(', ')}`).toEqual([]);
  });
});

describe('배치 캐논 ③ — 스크롤은 카드 몸통이 한다', () => {
  it('카드마다 몸통이 하나씩 있다', () => {
    const all = TSX();
    const cards = (all.match(/className="kb-card/g) ?? []).length;
    const bodies = (all.match(/kb-cb/g) ?? []).length;
    /* 피드는 몸통을 «겸한다»(`Feed.tsx` 가 `kb-cb kb-feed` 로 선다) — 그래서
       파일별이 아니라 전체 수로 센다. 수가 어긋나면 어느 카드가 몸통 없이
       `overflow: hidden` 안에 갇혔거나, 한 카드에 스크롤이 둘이라는 뜻이다. */
    expect(bodies, `카드 ${cards} 개 대 몸통 ${bodies} 개`).toBe(cards);
  });

  it('머리와 컨트롤 줄은 줄어들지 않는다', () => {
    const css = CSS();
    const bad = ['.kb-ch', '.kb-pills', '.kb-filt'].filter((s) => !/flex:\s*none/.test(block(css, s)));
    expect(bad, `몸통 대신 줄어드는 줄: ${bad.join(', ')}`).toEqual([]);
  });

  it('몸통은 «내용보다 작아질 수» 있다', () => {
    /* `min-height: 0` 이 없으면 `auto` 가 내용 높이를 바닥으로 삼아, 스크롤
       상자가 스크롤을 안 한다 — 대신 열이 넘친다. */
    const b = block(CSS(), '.kb-cb');
    expect(/min-height:\s*0/.test(b) && /overflow-y:\s*auto/.test(b)).toBe(true);
  });
});

describe('배치 캐논 ④ — 남는 높이는 가중치로 나눈다', () => {
  it('가중치·고정 클래스가 실제로 쓰인다', () => {
    /* 이 셋은 `kb-` 로 시작하지 않아 죽은-CSS 가드가 안 본다. 캐논을 지탱하는
       클래스라 여기서 따로 센다. */
    const all = TSX();
    /* ★정규식 리터럴로 짠다 — 템플릿 리터럴 안의 역슬래시는 이 파일을 쓰는
       길에서 한 번 먹혔고, 먹히면 `\b` 가 낱말 경계가 아니라 백스페이스가 되어
       **아무 자리도 못 찾는데 초록** 이 된다(2026-09-30 실측). */
    const worn = [...all.matchAll(/className="(kb-card[^"]*)"/g)].map((m) => m[1].split(' '));
    const gone = ['w2', 'w3', 'fix'].filter((c) => !worn.some((cl) => cl.includes(c)));
    expect(gone, `CSS 만 있고 아무도 안 붙인다: ${gone.join(', ')}`).toEqual([]);
  });

  it('탄력 카드는 기준 0 에서 자란다 — 그래야 «비례» 다', () => {
    /* `flex-basis: auto` 면 기준이 내용 높이라, 긴 목록 하나가 남는 높이까지
       더 먹어 열을 독차지한다(실측: 딜러 카드 1,561px). */
    expect(/\.kb-mid > \.kb-card,[^{]*\{[^}]*flex:\s*1 1 0/.test(CSS())).toBe(true);
  });

  it('카드·그림 바닥이 한 곳에서 온다', () => {
    const css = CSS();
    for (const v of ['--kb-card-min', '--kb-plot-min']) {
      expect(new RegExp(v + ': *[0-9]+px').test(css), `${v} 가 없다`).toBe(true);
    }
  });
});
