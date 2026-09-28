/**
 * 화면을 «재는» 도구 — 대비 · 넘침 · 글자 폭. [2026-09-28 디자인 문법 레인]
 *
 * 왜 도구로 남기나
 *   `compare_screens` 는 두 화면이 같은 «수» 를 말하는지 세고, `shot_screen` 은
 *   사람이 볼 그림을 찍는다. 그 둘 사이에 아무도 안 보는 자리가 있다 —
 *   **색이 읽히는가**(대비)와 **글자가 칸을 넘는가**(넘침)다. 둘 다 눈으로는
 *   놓치기 쉽고(특히 다크 스킴), 숫자로는 즉시 드러난다.
 *
 *   v2 는 이것을 `guards/contrast.test.ts` 로 잰다. 그런데 그 시험은 «토큰 값» 을
 *   재지 «화면» 을 재지 않는다. CDS 가 팔레트를 인라인으로 심고 스킴마다 면의
 *   역할이 뒤집히는 이 앱에서는, 실제로 그려진 픽셀 위에서 재야 답이 맞는다.
 *
 * 무엇을 재나
 *   (a) 대비 — 글자색 대 «투명이 아닌 첫 조상 배경». WCAG 2.2 기준 글자 4.5:1,
 *       그래픽(점·막대) 3:1. 재기 전에 `void document.body.offsetHeight` 로 배치를
 *       한 번 끝낸다(안 그러면 방금 바뀐 스킴의 옛 값이 나온다).
 *   (b) 넘침 — `scrollWidth > clientWidth + 1` 인 칸 수. 말줄임을 걷어낸 뒤에도
 *       칸이 모자라면 «글자가 이웃 위로 넘친다» 는 뜻이고, 그건 잘림과 같은 등급의
 *       결함이다(v2 「말줄임 절대 금지」 3).
 *   (c) `CH_PX` — 숫자 칸에서 `0` 한 글자의 실제 advance. 서식 최대치로 열 폭을
 *       잡으려면 이 수가 있어야 하고, **재는 대상이 곧 그리는 대상이어야 한다**
 *       (v2 `columns.ts` 의 ch 판례 — 한 표에서 ch 가 셋이었다).
 *
 * 쓰는 법 (compare_screens 와 같은 판)
 *   node probe_screen.mjs [화면URL] [API] [탭...]
 *     node probe_screen.mjs http://127.0.0.1:3400/ http://127.0.0.1:8302 메인 동향 국고 크레딧
 *   두 스킴을 다 돈다 — 라이트에서 통과한 색이 다크에서 떨어지는 일이 흔하다.
 */
const CDP = 'http://127.0.0.1:9222';
const URL_ = process.argv[2] || 'http://127.0.0.1:3400/';
const API = process.argv[3] || 'http://127.0.0.1:8302';
const TABS = process.argv.slice(4).length ? process.argv.slice(4) : ['메인', '동향', '국고', '크레딧'];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * 재는 자리 — [이름, 선택자, 최소 대비, 'fill'?].
 *
 * ★넷째 칸이 'fill' 이면 **채움색**을 잰다(글자색이 아니라). 상태 점·막대처럼
 *   글자가 없는 표식은 «제 배경 대 부모 배경» 이 읽히느냐가 전부고, 글자색을 재면
 *   상속된 색을 제 배경에 대고 재는 셈이라 뜻 없는 수가 나온다(2026-09-28 실측:
 *   점이 1.86:1 로 나왔는데 그건 잉크 대 청록이었다). WCAG 1.4.11 은 그래픽에
 *   3:1 을 요구하고, 그 «그래픽» 이 이 채움이다.
 */
const SPOTS = [
  ['부호 ↑', '.sr-up', 4.5],
  ['부호 ↓', '.sr-down', 4.5],
  ['부호 0', '.sr-flat', 4.5],
  ['매도', '.kb-side-s', 4.5],
  ['매수', '.kb-side-b', 4.5],
  ['이벤트 크로스', '.kb-evk.cross', 4.5],
  ['이벤트 체결', '.kb-evk.fill', 4.5],
  ['관심 별', '.kb-star.on', 4.5],
  ['상태 점', '.kb-dot.on', 3.0, 'fill'],
  ['표 머리', '.kb-tbl th', 4.5],
  ['뮤트 글', '.kb-n', 4.5],
  ['피드 칸', '.kb-c', 4.5],
  ['현재 탭', '.sr-navitem[data-on="true"], .kb-seg button.on', 4.5],
  ['켠 필터', '.sr-pillbtn[data-on="true"], .kb-filt button.on', 4.5],
  ['배지', '.kb-badge', 4.5],
  ['스트립 값', '.sr-strip-v', 4.5],
];

/** 넘침을 보는 칸 — 원문 둘은 뺀다(09-22 오너 수용: 잘리고 툴팁이 전체를 준다). */
const OVERFLOW_SEL =
  '.kb-tbl td, .kb-tbl th, .kb-c:not(.raw), .kb-li > span, .kb-li2 .sub, .kb-ev > *, .kb-tp > *:not(.kb-tpr), .kb-kvc, .kb-quad > div';

const t = await (await fetch(`${CDP}/json/new?${URL_}`, { method: 'PUT' })).json();
const ws = new WebSocket(t.webSocketDebuggerUrl);
let id = 0;
const waits = new Map();
const send = (method, params = {}) =>
  new Promise((res) => {
    const i = ++id;
    waits.set(i, res);
    ws.send(JSON.stringify({ id: i, method, params }));
  });
ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if (m.id && waits.has(m.id)) {
    waits.get(m.id)(m.result);
    waits.delete(m.id);
  }
};
await new Promise((r) => (ws.onopen = r));
await send('Network.enable');
await send('Network.setCacheDisabled', { cacheDisabled: true });
await send('Emulation.setDeviceMetricsOverride', { width: 1500, height: 1100, deviceScaleFactor: 1, mobile: false });
const ev = async (expr) =>
  (await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }))?.result?.value;

/* 브라우저 안에서 도는 잣대. 색 계산을 노드로 가져오지 않는 이유는 «푼 색» 이
   브라우저에만 있어서다 — `getComputedStyle` 이 `rgb()` 로 풀어 준 값을 그대로 쓴다. */
const MEASURE = `
(() => {
  void document.body.offsetHeight;                 // 배치를 한 번 끝낸다
  const lum = (c) => {
    const f = (v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
    return 0.2126 * f(c[0] / 255) + 0.7152 * f(c[1] / 255) + 0.0722 * f(c[2] / 255);
  };
  const parse = (s) => {
    const m = /rgba?\\(([^)]+)\\)/.exec(s || '');
    if (!m) return null;
    const p = m[1].split(/[,\\/\\s]+/).filter(Boolean).map(Number);
    return { rgb: [p[0], p[1], p[2]], a: p.length > 3 ? p[3] : 1 };
  };
  /** 투명이 아닌 첫 조상 배경 — 반투명이면 그 아래와 섞는다(틴트 셀이 그렇다). */
  const bgOf = (el) => {
    let cur = el, acc = null;
    while (cur) {
      const p = parse(getComputedStyle(cur).backgroundColor);
      if (p && p.a > 0) {
        acc = acc == null ? { rgb: p.rgb, a: p.a } : acc;
        if (p.a >= 0.999) return acc.a >= 0.999 ? acc.rgb : acc.rgb.map((v, i) => acc.a * v + (1 - acc.a) * p.rgb[i]);
        if (acc !== null && acc.a < 0.999) {
          const b = p.rgb;
          acc = { rgb: acc.rgb.map((v, i) => acc.a * v + (1 - acc.a) * b[i]), a: 1 };
          return acc.rgb;
        }
      }
      cur = cur.parentElement;
    }
    return acc ? acc.rgb : [255, 255, 255];
  };
  const ratio = (fg, bg) => {
    const a = lum(fg), b = lum(bg);
    return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  };
  const spots = __SPOTS__;
  const out = [];
  for (const [name, sel, min, kind] of spots) {
    let els = [];
    try { els = [...document.querySelectorAll(sel)]; } catch { continue; }
    els = els.filter((e) => e.offsetParent !== null && (e.textContent || '').trim() !== '' || (e.offsetWidth && e.offsetHeight && !(e.textContent || '').trim()));
    if (!els.length) continue;
    let worst = null;
    for (const e of els.slice(0, 40)) {
      const cs = getComputedStyle(e);
      /* 그래픽이면 «제 채움 대 부모 배경», 글자면 «제 글자색 대 제 배경». */
      const fgp = parse(kind === 'fill' ? cs.backgroundColor : cs.color);
      if (!fgp) continue;
      const bg = kind === 'fill' ? bgOf(e.parentElement || e) : bgOf(e);
      const fg = fgp.a >= 0.999 ? fgp.rgb : fgp.rgb.map((v, i) => fgp.a * v + (1 - fgp.a) * bg[i]);
      const r = ratio(fg, bg);
      if (!worst || r < worst.r) {
        /* 어느 «면» 위에서 떨어지는지까지 적는다 — 색 이름만으로는 고칠 자리를
           못 찾는다(실측: 같은 뮤트 글자가 카드 위 5.87, 컨트롤 면 위 4.47). */
        let where = '';
        for (let c = e; c && !where; c = c.parentElement) {
          const b = parse(getComputedStyle(c).backgroundColor);
          if (b && b.a > 0) where = String(c.className || c.tagName).trim().split(/\s+/).slice(0, 2).join('.');
        }
        worst = { r, txt: (e.textContent || '').trim().slice(0, 14), where, bg: 'rgb(' + bg.map(Math.round).join(',') + ')' };
      }
    }
    if (worst) out.push({ name, n: els.length, r: Math.round(worst.r * 100) / 100, min, txt: worst.txt, where: worst.where, bg: worst.bg, ok: worst.r >= min });
  }
  /* 넘침 — ★찾는 것은 «조용한 잘림» 이다.
     «…» 로 잘렸다는 사실을 보이고 마우스를 올리면 전체가 뜨는 칸은 규칙을 지킨
     것이다(v2 「말줄임 절대 금지」가 금지하는 것은 소리 없이 사라지는 글자다).
     그래서 text-overflow: ellipsis 와 title 을 **둘 다** 가진 칸은 세지 않는다 —
     둘 중 하나만 있으면 잡는다(잘렸는데 전체를 볼 길이 없거나, 그냥 사라지거나). */
  const excused = (e) => {
    if (getComputedStyle(e).textOverflow !== 'ellipsis') return false;
    for (let c = e; c; c = c.parentElement) if (c.getAttribute && c.getAttribute('title')) return true;
    return false;
  };
  const ov = [...document.querySelectorAll(__OVER__)]
    .filter((e) => e.offsetParent !== null && e.scrollWidth > e.clientWidth + 1 && !excused(e))
    .map((e) => ({ cls: e.className || e.tagName, w: e.clientWidth, s: e.scrollWidth, txt: (e.textContent || '').trim().slice(0, 18) }));
  /* CH_PX — 숫자 칸에서 '0' 한 글자의 실제 폭 */
  let ch = null;
  const cell = document.querySelector('.kb-tbl td.num, .kb-tbl td, .kb-c.num');
  if (cell) {
    const s = document.createElement('span');
    s.textContent = '0000000000';
    s.style.cssText = 'position:absolute;visibility:hidden;white-space:pre';
    cell.appendChild(s);
    ch = Math.round((s.getBoundingClientRect().width / 10) * 100) / 100;
    s.remove();
  }
  return { spots: out, overflow: ov, ch };
})()
`.replace('__SPOTS__', JSON.stringify(SPOTS)).replace('__OVER__', JSON.stringify(OVERFLOW_SEL));

await sleep(1200);
await ev(`localStorage.setItem('kbond.base', ${JSON.stringify(API)}); localStorage.removeItem('kbond.tok'); 1`);

let fails = 0;
for (const scheme of ['light', 'dark']) {
  await ev(`localStorage.setItem('kbond.scheme', ${JSON.stringify(scheme)}); 1`);
  await send('Page.navigate', { url: URL_ });
  await sleep(6500);
  for (const tab of TABS) {
    const clicked = await ev(
      `(()=>{const b=[...document.querySelectorAll('.kb-seg button')].find(x=>x.textContent.includes(${JSON.stringify(tab)}));
        if(!b) return 'no-tab'; b.click(); return 'ok';})()`,
    );
    await sleep(tab === '메인' ? 3000 : 6500);
    const r = await ev(MEASURE);
    if (!r) { console.log(`[${scheme}] ${tab}: 측정 실패`); continue; }
    const bad = r.spots.filter((s) => !s.ok);
    fails += bad.length + r.overflow.length;
    console.log(`\n── ${scheme} · ${tab} ${clicked === 'no-tab' ? '(탭 없음)' : ''} · CH_PX ${r.ch ?? '—'}`);
    for (const s of r.spots) {
      console.log(
        `   ${s.ok ? ' ' : '✗'} ${s.name.padEnd(12)} ${String(s.r).padStart(6)} : 1  (필요 ${s.min}, n=${s.n}` +
          `, "${s.txt}"${s.ok ? '' : ` · ${s.where} ${s.bg}`})`,
      );
    }
    if (r.overflow.length) {
      /* 같은 칸이 수십 줄에서 같은 이유로 넘치므로 «칸 종류» 로 접어 센다 —
         여든 줄을 늘어놓으면 종류가 몇인지가 안 보인다. */
      const by = new Map();
      for (const o of r.overflow) {
        const k = o.cls;
        const e = by.get(k) || { n: 0, worst: o };
        e.n++;
        if (o.s - o.w > e.worst.s - e.worst.w) e.worst = o;
        by.set(k, e);
      }
      console.log(`   ✗ 넘침 ${r.overflow.length}칸 · 종류 ${by.size}`);
      for (const [k, e] of [...by.entries()].sort((a, b) => b[1].n - a[1].n)) {
        console.log(`       ${String(e.n).padStart(3)}줄  ${k}  ${e.worst.w}<${e.worst.s}  "${e.worst.txt}"`);
      }
    } else {
      console.log('     넘침 0');
    }
  }
}
console.log(`\n합계 위반 ${fails}건`);
await fetch(`${CDP}/json/close/${t.id}`);
ws.close();
/* ★`process.exit()` 를 부르지 않는다 — 닫는 중인 WebSocket 핸들 위에서 libuv 가
   `!(handle->flags & UV_HANDLE_CLOSING)` 로 죽는다(실측). 종료 코드만 남기고
   이벤트 루프가 스스로 비도록 둔다. */
process.exitCode = fails ? 1 : 0;
