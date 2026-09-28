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
   */
  const NAME_CELLS = ['.kb-c.n', '.kb-c.who', '.kb-c.h', '.kb-c.raw', '.kb-c.mat',
    '.kb-li .nm', '.kb-tp > .kb-tpr', '.kb-evt', '.kb-tbl td.nm'];

  it('말줄임은 이름 칸에만 있다', () => {
    const css = stripComments(read(path.relative(ROOT, KBOND_CSS)));
    const sels: string[] = [];
    for (const m of css.matchAll(/([^{}]+)\{([^}]*)\}/g)) {
      if (/text-overflow:\s*ellipsis/.test(m[2])) sels.push(m[1].trim());
    }
    const unknown = sels.filter((s) => !s.split(',').every((one) => NAME_CELLS.includes(one.trim())));
    expect(unknown, `허용 밖의 말줄임: ${unknown.join(' | ')}`).toEqual([]);
  });

  it('잘리는 칸은 title 로 전체를 준다', () => {
    const all = tsxAll();
    for (const cls of ['kb-c n', 'kb-c who', 'kb-c h', 'kb-c raw', 'l nm']) {
      const re = new RegExp(`className="${cls}"[^>]*title=`);
      expect(re.test(all), `${cls} 에 title 이 없다 — 잘리면 전체를 볼 길이 없다`).toBe(true);
    }
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
