import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { stripComments, walk } from './_source';

/**
 * 화면 문법의 나머지 — 색 · 토큰 · 표 · 죽은 CSS.
 *
 * 차트는 `chart-canon`, 서식은 `format-single-source` 가 잰다. 여기는 그 둘이
 * 안 보는 자리다.
 */

const ROOT = path.resolve(import.meta.dirname, '..');
const SRC = path.join(ROOT, 'src');
const KBOND_CSS = path.join(ROOT, 'src', 'theme', 'kbond.css');
const rel = (f: string) => path.relative(ROOT, f);
const read = (f: string) => fs.readFileSync(path.join(ROOT, f), 'utf8');
const code = (f: string) => stripComments(read(f));

const tsxAll = () =>
  walk(SRC, ['.tsx'])
    .map((f) => read(rel(f)))
    .join('\n');

describe('색은 «부호와 매매» 에만', () => {
  /**
   * `.sr-up`/`.sr-down` 은 **부호**의 클래스다. 매매(옆)는 `.kb-side-*` 가 진다 —
   * 같은 색이지만 다른 이름이라, 한 카드에서 둘이 같이 서도 코드가 어느 뜻인지
   * 말해 준다. 그 밖의 쓰임(이벤트 종류·스왑 다리·검산·오류문)은 **셋째 뜻**이고,
   * 셋째 뜻은 앞의 둘까지 흐린다 [2026-09-28 에 다섯 자리를 걷었다].
   */
  it('방향색 클래스는 부호에만 붙는다', () => {
    const offenders: string[] = [];
    for (const f of walk(SRC, ['.tsx']).map(rel)) {
      code(f)
        .split('\n')
        .forEach((line, i) => {
          if (!/['"`\s](sr-up|sr-down)['"`\s]/.test(line)) return;
          /* 부호 판정과 같은 줄에 있으면 부호다(`v < 0 ? 'sr-down' : 'sr-up'`). */
          if (/[<>]\s*0|bpe|dbp|vs_prev|\bv\b\s*[<>]|med|imb/.test(line)) return;
          offenders.push(`  ${f}:${i + 1}  ${line.trim()}`);
        });
    }
    expect(
      offenders,
      `방향색이 부호 아닌 뜻에 쓰였다 — 매매는 .kb-side-*, 범주는 --sr-ref-*:\n${offenders.join('\n')}`,
    ).toEqual([]);
  });

  it('방향색을 쓰는 CSS 는 부호·매매·틴트뿐이다', () => {
    const css = stripComments(read(path.relative(ROOT, KBOND_CSS)));
    const ALLOWED = /\.kb-side-|\.kb-sb|\.kb-q|\.kb-pt|--kb-p-|\.kb-hmleg/;
    /* ★줄이 아니라 «규칙» 으로 본다 — 선택자는 값보다 윗줄에 있어서, 줄 단위로
       보면 `.kb-sb` 의 막대처럼 허용된 것이 잘못 걸린다(첫 판에서 그랬다). */
    const offenders: string[] = [];
    for (const m of css.matchAll(/([^{}]+)\{([^}]*)\}/g)) {
      const sel = m[1].trim();
      if (!/var\(--sr-(up|down)\)/.test(m[2])) continue;
      if (ALLOWED.test(sel)) continue;
      offenders.push(`  ${sel}`);
    }
    expect(offenders, `방향색이 허용 밖에서 쓰였다:\n${offenders.join('\n')}`).toEqual([]);
  });

  it('틴트 위 글자는 잉크다 — 히트맵이 색을 직접 칠하지 않는다', () => {
    /* v2 `theme/tint.ts` 실측: 같은 부호 틴트 위의 방향색 글자는 어느 농도에서도
       4.5:1 을 못 넘는다. 농도 문제가 아니라 범주적 규칙이다. */
    const heat = code(path.join('src', 'components', 'Heat.tsx'));
    expect(heat, 'Heat 가 틴트를 손으로 섞는다').not.toMatch(/color-mix/);
    expect(heat, 'Heat 가 글자에 색을 준다').not.toMatch(/color:\s*`/);
    expect(heat, 'Heat 가 v2 램프를 안 쓴다').toMatch(/tintFor\(/);
  });
});

describe('토큰', () => {
  it('반지름은 CDS 스케일에서만 온다', () => {
    /* 같은 수를 px 로 다시 적는 것도 실패다 — 값이 같아도 «출처» 가 다르면
       스케일이 바뀔 때 한쪽만 따라간다(v2 `guards/radius-scale`). */
    const ALLOWED = new Set(['0', '50%', '999px']);
    const css = stripComments(read(path.relative(ROOT, KBOND_CSS)));
    const bad: string[] = [];
    for (const m of css.matchAll(/border-radius:\s*([^;]+);/g)) {
      for (const v of m[1].trim().split(/\s+/)) {
        if (!v || ALLOWED.has(v) || v.startsWith('var(--borderRadius-')) continue;
        bad.push(m[1].trim());
      }
    }
    expect([...new Set(bad)], 'CDS 스케일 밖의 반지름').toEqual([]);
  });

  it('글자 크기는 CDS 사다리에서만 온다', () => {
    /* 빽빽한 칸은 11·12·13·14, 그 위는 CDS 의 단 그대로 — headline 16 · title3 20 ·
       title1 28. **반픽셀은 없다**: 같은 단이 두 개가 되고, 둘 중 어느 것이 «그 단»
       인지 다음 사람이 알 길이 없다(걷기 전 이 파일에 9.5·11.5·12.5·13.5 가 있었다). */
    const LADDER = [11, 12, 13, 14, 16, 20, 28];
    const css = stripComments(read(path.relative(ROOT, KBOND_CSS)));
    const sizes = [...css.matchAll(/font-size:\s*([\d.]+)px/g)].map((m) => Number(m[1]));
    const bad = [...new Set(sizes.filter((s) => !LADDER.includes(s)))].sort((a, b) => a - b);
    expect(bad, `사다리(${LADDER.join('·')}) 밖 글자 크기: ${bad.join(', ')}`).toEqual([]);
  });

  it('「선택됨」은 한 가지 면이다', () => {
    const css = stripComments(read(path.relative(ROOT, KBOND_CSS)));
    expect(css, 'CDS 파랑 워시가 남아 있다 — 이 앱에서 파랑은 낱말이다').not.toMatch(/bgPrimaryWash/);
  });

  it('포커스 링은 잉크 하나다', () => {
    const css = stripComments(read(path.relative(ROOT, KBOND_CSS)));
    const rings = [...css.matchAll(/:focus-visible[^{]*\{([^}]*)\}/g)].map((m) => m[1]);
    const bad = rings.filter((r) => /outline:/.test(r) && !/var\(--color-fg\)/.test(r));
    expect(bad, `잉크가 아닌 포커스 링: ${bad.join(' | ')}`).toEqual([]);
  });
});

describe('표', () => {
  it('모든 .kb-tbl 은 폭을 ColGroup 에서 받는다', () => {
    /* `table-layout: fixed` 인데 폭을 안 주면 열이 **똑같이** 나뉜다 — 종목명은
       잘리고 「나이」는 텅 빈다. 그것이 2026-09-28 이전의 상태였다. */
    const offenders: string[] = [];
    for (const f of walk(SRC, ['.tsx']).map(rel)) {
      const body = code(f);
      /* 여는 태그와 `<ColGroup>` 사이에 주석이 낄 수 있다 — 왜 그 폭인지 적는
         자리다. 주석은 `stripComments` 가 지워 빈 `{}` 만 남으므로 그것을 건너뛴다. */
      for (const m of body.matchAll(/<table className="kb-tbl">(?:\s|\{|\})*([\s\S]{0,60})/g)) {
        if (!m[1].includes('<ColGroup')) offenders.push(`${f}: ${m[1].trim().slice(0, 40)}`);
      }
    }
    expect(offenders, `폭 없는 표:\n  ${offenders.join('\n  ')}`).toEqual([]);
  });

  it('인라인 px 폭을 쓰지 않는다', () => {
    const offenders: string[] = [];
    for (const f of walk(SRC, ['.tsx']).map(rel)) {
      code(f)
        .split('\n')
        .forEach((line, i) => {
          if (/style=\{\{\s*width:\s*\d+\s*\}\}/.test(line)) offenders.push(`  ${f}:${i + 1}  ${line.trim()}`);
        });
    }
    expect(offenders, `폭은 lib/columns 가 정한다:\n${offenders.join('\n')}`).toEqual([]);
  });

  it('표 머리는 700 muted 다', () => {
    const css = stripComments(read(path.relative(ROOT, KBOND_CSS)));
    const th = /\.kb-tbl th \{([^}]*)\}/.exec(css);
    expect(th, '.kb-tbl th 규칙이 없다').not.toBeNull();
    expect(th![1]).toMatch(/font-weight:\s*700/);
    expect(th![1]).toMatch(/color:\s*var\(--color-fgMuted\)/);
  });
});

describe('말줄임 — 조용한 잘림만 금지', () => {
  /**
   * 규칙이 금지하는 것은 **소리 없이 사라지는 글자**다. 이름처럼 «서식이 아니라
   * 자료» 인 칸은 어떤 폭도 모자랄 수 있어서, 셋을 함께 갖추면 지킨 것으로 본다:
   * 실측 최대치까지 넓히고 · «…» 로 잘렸음을 보이고 · `title` 이 전체를 준다.
   *
   * ★이 묶음은 2026-09-30 에 **거꾸로 서 있었다**. 「말줄임이 허용 칸에만 있나」와
   *   「허용 칸에 title 이 있나」만 물었고 — 둘 다 **예외 목록**을 재는 질문이다 —
   *   정작 금지 대상인 「«…» 없이 잘리는 칸이 있나」는 묻지 않았다. 그래서 초록
   *   아래에 다섯 자리가 살아 있었다(`.kb-tp` 의 데스크 둘·원문 둘 · `.kb-ev` 의
   *   데스크 · `.kb-swr` 의 다리 · `.kb-li .nm` 은 «…» 는 보이는데 전문이 없었다).
   *   아래 첫 시험이 그 질문이다 — 목록이 아니라 **CSS 전체**를 훑는다.
   */

  /** 잘리는 칸 = `overflow: hidden` + `white-space: nowrap`. */
  const clippers = (css: string) => {
    const out: { sel: string; body: string }[] = [];
    for (const m of css.matchAll(/([^{}]+)\{([^}]*)\}/g)) {
      const body = m[2];
      if (!/overflow(-x)?:\s*hidden/.test(body)) continue;
      if (!/white-space:\s*nowrap/.test(body)) continue;
      out.push({ sel: m[1].trim(), body });
    }
    return out;
  };

  /**
   * 「무리 클리퍼」 — 칸 여럿을 한 번에 자르는 규칙. 자기 몸에 «…» 가 없어도 되지만,
   * **자르는 칸마다** «…» 를 가진 자식 규칙을 여기 적어야 한다. 숫자 칸은 서식
   * 최대치로 맞췄으니 자를 일이 없다(규칙 ①) — 그래서 이름 칸만 적는다.
   */
  const GROUPS: Record<string, string[]> = {
    '.kb-c': ['.kb-c.n', '.kb-c.who', '.kb-c.h', '.kb-c.raw', '.kb-c.mat'],
    '.kb-li > span': ['.kb-li .nm'],
    '.kb-tp > *': ['.kb-tp > .kb-tpr', '.kb-dk'],
    '.kb-ev > *': ['.kb-evt', '.kb-dk'],
  };

  it('«…» 없이 잘리는 칸이 없다 — 규칙 쪽에서 묻는다', () => {
    const css = stripComments(read(path.relative(ROOT, KBOND_CSS)));
    const ell = new Set(
      [...css.matchAll(/([^{}]+)\{([^}]*)\}/g)]
        .filter((m) => /text-overflow:\s*ellipsis/.test(m[2]))
        .flatMap((m) => m[1].split(',').map((one) => one.trim())),
    );
    const bad: string[] = [];
    for (const { sel, body } of clippers(css)) {
      if (/text-overflow:\s*ellipsis/.test(body)) continue; /* 스스로 지킨다 */
      const kids = GROUPS[sel];
      if (!kids) {
        bad.push(`  ${sel} — «…» 도 없고 GROUPS 등록도 없다`);
        continue;
      }
      for (const k of kids) {
        if (!ell.has(k)) bad.push(`  ${sel} → ${k} — 등록됐는데 «…» 규칙이 없다`);
      }
    }
    expect(bad, `조용히 잘리는 칸 — ${bad.join(' | ')}`).toEqual([]);
  });

  it('말줄임은 이름 칸에만 있다', () => {
    const css = stripComments(read(path.relative(ROOT, KBOND_CSS)));
    const sels: string[] = [];
    for (const m of css.matchAll(/([^{}]+)\{([^}]*)\}/g)) {
      if (/text-overflow:\s*ellipsis/.test(m[2])) sels.push(m[1].trim());
    }
    const allowed = [...new Set(Object.values(GROUPS).flat())].concat([
      /* 스스로 자르고 스스로 «…» 를 갖는 칸들. */
      '.kb-tbl td.nm', '.kb-swr .w', '.kb-dk',
    ]);
    const unknown = sels.filter((s) => !s.split(',').every((one) => allowed.includes(one.trim())));
    expect(unknown, `허용 밖의 말줄임: ${unknown.join(' | ')}`).toEqual([]);
  });

  /**
   * 규칙 ③ — 잘린 칸은 «마우스를 올리면 전체가 뜬다».
   *
   * 칸 자신이 `title` 을 가지거나, 행이 갖고 **그 title 이 이 칸의 자료를 담아야**
   * 한다. 셋째 조건이 없으면 초록인데도 이름을 볼 길이 없다 — `.kb-li .nm` 이
   * 그랬다(행 title 이 데스크·나이뿐이라 종목 이름만 빠졌다).
   */
  /**
   * 여는 태그를 «자리마다» 집는다. 존재 검사(`정규식.test(전체)`)로는 안 된다 —
   * 같은 클래스가 여러 파일에 있으면 한 자리만 지켜도 초록이 된다(2026-09-30 에
   * 이 시험의 첫 판이 바로 그랬다: `.kb-dk` 의 title 을 한 곳에서 떼도 통과했다).
   */
  const tags = (src: string, cls: string): string[] => {
    /* ★«낱말» 로 맞춘다 — 문자열이 꼭 같아야 잡던 첫 판은 `className="l nm kb-n"`
       (크레딧 종류 칸)을 놓쳤다. 칸에 클래스가 하나 더 붙었다고 규칙 밖이 되면
       자가 아니다. */
    const want = cls.split(' ');
    const out: string[] = [];
    const re = /className="([^"]*)"/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(src))) {
      const have = m[1].split(' ');
      if (!want.every((c) => have.includes(c))) continue;
      const lt = src.lastIndexOf('<', m.index);
      let depth = 0;
      let end = m.index;
      for (let q = lt; q < src.length; q++) {
        const ch = src[q];
        if (ch === '{') depth++;
        else if (ch === '}') depth--;
        else if (ch === '>' && depth === 0) { end = q; break; }
      }
      out.push(src.slice(lt, end + 1));
    }
    return out;
  };

  /** CSS 에서 «…» 를 받는 칸 ↔ JSX 가 그 칸에 붙이는 클래스. */
  const TITLED: { what: string; cls: string }[] = [
    { what: '.kb-c.n', cls: 'kb-c n' },
    { what: '.kb-c.who', cls: 'kb-c who' },
    { what: '.kb-c.h', cls: 'kb-c h' },
    { what: '.kb-c.raw', cls: 'kb-c raw' },
    { what: '.kb-c.mat', cls: 'kb-c num mat' },
    { what: '.kb-tbl td.nm', cls: 'l nm' },
    { what: '.kb-tp > .kb-tpr', cls: 'kb-tpr' },
    { what: '.kb-dk', cls: 'kb-n kb-dk' },
    { what: '.kb-swr .w', cls: 'w' },
    { what: '.kb-swr .w.r', cls: 'w r' },
    /* 이벤트 문장·사다리 이름은 **행** 이 title 을 진다 — 그 title 이 칸의 식을
       담는지까지 본다(다음 시험). */
  ];

  it('잘리는 칸은 자리마다 title 로 전체를 준다', () => {
    const bad: string[] = [];
    for (const f of walk(SRC, ['.tsx']).map(rel)) {
      const src = read(f);
      for (const { what, cls } of TITLED) {
        tags(src, cls).forEach((t) => {
          if (!/\stitle=/.test(t)) bad.push(`  ${f}  ${what}  ${t.replace(/\s+/g, ' ').slice(0, 90)}`);
        });
      }
    }
    expect(bad, `title 없이 잘리는 자리 — ${bad.join(' || ')}`).toEqual([]);
  });

  it('«…» 를 받는 칸은 JSX 에 실제로 있다', () => {
    /* 위 시험은 «없으면 통과» 다(자리가 0 이면 셀 게 없다). 그래서 자리 수를 따로 센다 —
       클래스 이름이 바뀌면 이 시험이 먼저 빨개진다. */
    const all = tsxAll();
    const gone = TITLED.filter(({ cls }) => tags(all, cls).length === 0).map((t) => t.what);
    expect(gone, `CSS 는 «…» 를 주는데 JSX 에 그 칸이 없다: ${gone.join(', ')}`).toEqual([]);
  });

  it('행이 title 을 지는 칸은 그 행 title 이 칸의 자료를 담는다', () => {
    const all = tsxAll();
    /* 사다리 관심 줄 — 칸은 `{e.n}`, 행 title 은 그것을 담아야 한다. */
    const ax = all.match(/className="kb-li ax"[\s\S]{0,400}?title=\{`([^`]*)`\}/);
    expect(ax, '.kb-li ax 행에 title 이 없다').not.toBeNull();
    expect(ax![1], `.kb-li ax 의 title 에 종목 이름(e.n)이 없다: ${ax![1]}`).toContain('e.n');
    /* 이벤트 줄 — 칸과 행이 같은 식(`evText(e)`)이라야 툴팁이 그 문장이다. */
    expect(/className="kb-ev"[^>]*title=\{evText\(e\)\}/.test(all), '.kb-ev 행 title 이 evText 가 아니다').toBe(true);
    expect(/className="kb-evt">\{evText\(e\)\}/.test(all), '.kb-evt 칸이 evText 가 아니다').toBe(true);
  });
});

describe('죽은 CSS', () => {
  it('kbond.css 의 클래스는 전부 쓰인다', () => {
    const css = stripComments(read(path.relative(ROOT, KBOND_CSS)));
    const all = tsxAll();
    const names = [...new Set([...css.matchAll(/\.(kb-[a-z0-9-]+)/g)].map((m) => m[1]))];
    /* `.kb-ch-ctl` 은 머리에 컨트롤이 붙는 카드가 생기면 쓴다 — 자리표시자로 남긴다. */
    const dead = names.filter((n) => n !== 'kb-ch-ctl' && !all.includes(n));
    expect(dead, `아무도 안 붙이는 클래스: ${dead.join(', ')}`).toEqual([]);
  });

  it('붙이는 클래스는 규칙이 있다', () => {
    const css = read(path.relative(ROOT, KBOND_CSS));
    const all = tsxAll();
    const used = [...new Set([...all.matchAll(/\b(kb-[a-z0-9-]+)\b/g)].map((m) => m[1]))];
    const norule = used.filter((u) => !css.includes(`.${u}`) && !u.startsWith('kb-p-') && u !== 'kb-cols');
    expect(norule, `규칙 없는 클래스(붙여 놓고 아무 일도 안 한다): ${norule.join(', ')}`).toEqual([]);
  });

  it('type.css 는 이 앱이 쓰는 것만 담는다', () => {
    /* v2 에서 통째로 베껴 온 파일이라, 안 쓰는 부품 CSS 가 남아 있으면 다음 사람이
       그 규칙을 «이 앱의 규칙» 으로 읽는다(2026-09-28 에 275 규칙을 걷었다). */
    const css = stripComments(read(path.join('src', 'theme', 'type.css')));
    const all = tsxAll() + read(path.relative(ROOT, KBOND_CSS));
    const names = [...new Set([...css.matchAll(/\.(sr-[a-z0-9-]+)/g)].map((m) => m[1]))];
    const dead = names.filter((n) => !all.includes(n));
    expect(dead, `이 앱이 안 쓰는 v2 부품 CSS: ${dead.join(', ')}`).toEqual([]);
  });
});
