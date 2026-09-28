import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { stripComments, walk } from './_source';

/**
 * 차트의 규율 셋 — 생김새 · 무게 · 모션.
 *
 * ── 왜 가드인가 ────────────────────────────────────────────────────────────
 * 셋 다 **조용히** 깨진다. 생김새는 한 차트만 다르게 그려도 화면이 도는 한 아무도
 * 안 알려 주고, 무게는 임포트 한 줄로 늘고(아래 ②의 실측), 모션은 넣는 순간
 * 「부드러워졌다」로 읽혀 되돌릴 이유를 못 찾는다.
 */

const ROOT = path.resolve(import.meta.dirname, '..');
const SRC = path.join(ROOT, 'src');
const rel = (f: string) => path.relative(ROOT, f);
const body = (f: string) => stripComments(fs.readFileSync(path.join(ROOT, f), 'utf8'));

describe('차트 캐논', () => {
  const files = walk(SRC, ['.ts', '.tsx']).map(rel);

  /* ── ① 라이브러리는 `src/chart` 안에서만 ───────────────────────────────── */
  it('lightweight-charts 는 src/chart 밖에서 안 불린다', () => {
    const hits = files.filter(
      (f) => !f.startsWith(path.join('src', 'chart')) && /from ['"]lightweight-charts['"]/.test(body(f)),
    );
    expect(hits, `차트 밖에서 라이브러리를 부른다: ${hits.join(', ')}`).toEqual([]);
  });

  /**
   * ── ② 본체 번들이 라이브러리를 물면 안 된다 ────────────────────────────
   *
   * ★실측 2026-09-28: `Curve.tsx` 가 `useLwChart` 에서 상수 **하나**를 가져오자
   *   메인 첫 화면의 JS 가 787KB → 964KB 가 됐다. 커브는 크레딧 탭의 정적
   *   임포트라 본체 번들에 있고, `useLwChart` 는 모듈 꼭대기에서 라이브러리를
   *   부르므로 라이브러리가 통째로 따라 들어온 것이다. 지연 로드가 통째로 무효.
   *
   *   그래서 «정적으로 실려 가는 파일» 은 라이브러리를 안 무는 모듈에서만 읽는다.
   *   수를 들고 있는 파일(`chart/metrics.ts`)과 순수 산술(`tenor*.ts`)이 그것이다.
   */
  const LIBRARY_FREE = ['metrics', 'tenor', 'tenorScale', 'stable'];
  it('정적으로 실리는 컴포넌트는 라이브러리 없는 차트 모듈만 읽는다', () => {
    const lazy = new Set(['PxChart.tsx', 'PulseChart.tsx']); // next/dynamic 으로만 들어온다
    const offenders: string[] = [];
    for (const f of files.filter((x) => x.startsWith(path.join('src', 'components')))) {
      if (lazy.has(path.basename(f))) continue;
      for (const m of body(f).matchAll(/from ['"]@\/chart\/([A-Za-z]+)['"]/g)) {
        if (!LIBRARY_FREE.includes(m[1])) offenders.push(`${f} → @/chart/${m[1]}`);
      }
    }
    expect(
      offenders,
      `정적 컴포넌트가 라이브러리를 무는 모듈을 읽는다(첫 화면이 무거워진다):\n  ${offenders.join('\n  ')}`,
    ).toEqual([]);
  });

  it('라이브러리 없는 모듈은 정말로 라이브러리를 안 문다', () => {
    const offenders = LIBRARY_FREE.map((n) => path.join('src', 'chart', `${n}.ts`))
      .filter((f) => fs.existsSync(path.join(ROOT, f)))
      .filter((f) => /^import [^t].*from ['"]lightweight-charts['"]/m.test(body(f)));
    expect(offenders, `값 임포트가 들어 있다: ${offenders.join(', ')}`).toEqual([]);
  });

  it('무거운 차트는 next/dynamic 으로만 들어온다', () => {
    for (const host of ['Bonds.tsx', 'Trends.tsx']) {
      const src = body(path.join('src', 'components', host));
      expect(src, `${host} 가 차트를 정적으로 부른다`).not.toMatch(/^import \{ (PxChart|PulseChart) \}/m);
      expect(src, `${host} 에 dynamic 임포트가 없다`).toMatch(/dynamic\(\(\) => import\('\.\/(PxChart|PulseChart)'\)/);
    }
  });

  /* ── ③ 생김새는 한 곳에서 나온다 ──────────────────────────────────────── */
  it('캐논 옵션은 한 곳뿐이다 — 격자 없음 · 오른쪽 축 · 조용한 눈금', () => {
    const canon = body(path.join('src', 'chart', 'useLwChart.ts'));
    expect(canon).toMatch(/grid: \{ vertLines: \{ visible: false \}, horzLines: \{ visible: false \} \}/);
    expect(canon).toMatch(/tickMarkDensity: TICK_DENSITY/);
    expect(canon).toMatch(/leftPriceScale: \{ visible: false \}/);
    expect(canon).toMatch(/horzLine: \{ visible: false, labelVisible: true \}/);
    /* 개별 차트가 제 옵션으로 캐논을 덮으면 생김새가 갈린다. */
    const others = files.filter(
      (f) => f.startsWith(path.join('src', 'chart')) && !f.endsWith('useLwChart.ts'),
    );
    const hits = others.filter((f) => /\bgrid:\s*\{|tickMarkDensity/.test(body(f)));
    expect(hits, `캐논 밖에서 격자·눈금을 정한다: ${hits.join(', ')}`).toEqual([]);
  });

  it('옛 SVG 차트의 클래스는 남아 있지 않다', () => {
    /* `.kb-grid`·`.kb-legend`·`.kb-tip` 은 09-23 판의 것이다. 살아 있으면 두 문법이
       한 앱에 공존한다는 뜻이고, 그게 이번에 없앤 그것이다. */
    const css = fs.readFileSync(path.join(ROOT, 'src', 'theme', 'kbond.css'), 'utf8');
    const dead = ['.kb-grid', '.kb-legend', '.kb-xhair', '.kb-px ', '.kb-actbar', '.kb-mpref'];
    const alive = dead.filter((c) => new RegExp(`^\\s*${c.replace('.', '\\.')}`, 'm').test(css));
    expect(alive, `옛 차트 CSS 가 남아 있다: ${alive.join(', ')}`).toEqual([]);
  });

  /* ── ④ 그림의 기하는 절대 애니메이션하지 않는다 ───────────────────────── */
  it('차트 기하에 transition 이 없다', () => {
    /* v2 `theme/motion.ts`: 「선이 움직이면 그건 장식이 아니라 데이터에 대한
       거짓말이 된다」 — 움직이는 동안 화면의 수는 어느 시점의 것도 아니다. */
    const css = fs.readFileSync(path.join(ROOT, 'src', 'theme', 'kbond.css'), 'utf8');
    const offenders: string[] = [];
    for (const m of css.matchAll(/([^{}]+)\{([^}]*)\}/g)) {
      const sel = m[1].trim();
      if (!/\.kb-(curve|pt|ax|xh|xl)\b|\.sr-plot\b/.test(sel)) continue;
      if (/transition|animation/.test(m[2])) offenders.push(sel);
    }
    expect(offenders, `그림에 모션이 걸려 있다: ${offenders.join(', ')}`).toEqual([]);
  });

  /* ── ⑤ 리드아웃은 그림 «밖» 한 줄이다 ─────────────────────────────────── */
  it('차트 화면은 떠 있는 카드 대신 스트립을 쓴다', () => {
    for (const f of ['PxChart.tsx', 'PulseChart.tsx', 'Curve.tsx']) {
      const src = body(path.join('src', 'components', f));
      expect(src, `${f} 에 리드아웃 스트립이 없다`).toMatch(/<ChartReadoutStrip/);
      expect(src, `${f} 가 떠 있는 말풍선을 쓴다`).not.toMatch(/className="kb-tip"/);
    }
  });
});
