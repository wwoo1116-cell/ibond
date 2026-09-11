/**
 * 두 화면 지문 대조 — 옛 화면(kbond_live.html)과 새 화면(kbond-web)이 «같은 책에서
 * 같은 수» 를 말하는지 기계가 센다. [React 전환 3단계 · 2026-09-11]
 *
 * 왜 필요한가
 *   전환 판정을 «나란히 띄워 놓고 눈으로 본다» 로 하면 사람이 못 본 칸이 남는다.
 *   옛 화면은 **자바스크립트가 책을 받아 스스로 접고**, 새 화면은 **서버가 접어 준
 *   값을 그린다**(kbond_view). 두 길이 같은 수에 도착하는지가 전환의 유일한 관문이다.
 *
 * 무엇을 세는가 — 화면에 «그려진» 글자다. API 응답이 아니다.
 *   1. 탭 숫자 여섯
 *   2. 히트맵 여덟 행 × 여섯 칸의 값과 건수
 *   3. 크레딧 분류 줄(종별·등급·건수·YTM·민평대비)
 *   4. 크레딧 오퍼 표 위 15줄
 *   5. 국고 종목 줄 위 15줄
 *
 * 어떻게 쓰나
 *   1) 동결 리플레이 백엔드를 띄운다(두 화면이 같은 책을 봐야 한다):
 *        set KBOND_REPLAY=20260903&& set KBOND_AT=15:30:00&& ^
 *          python -X utf8 -m uvicorn kbond_api:app --host 127.0.0.1 --port 8302
 *   2) 새 화면 정적 빌드를 :3400 으로 낸다(그 포트가 CORS 허용 목록에 있다):
 *        cd ..\kbond-web && npm run build && python -m http.server 3400 --directory out
 *   3) 헤드리스 크롬을 디버깅 포트로 띄운다:
 *        chrome --headless=new --remote-debugging-port=9222 --user-data-dir=<임시> about:blank
 *   4) node compare_screens.mjs [옛화면URL] [새화면URL] [API]
 *
 * ⚠새 화면은 저장된 주소가 코드에 구운 주소를 이긴다(`api.ts`). 그래서 여기서
 *   localStorage 에 API 를 먼저 박고 다시 연다 — 안 그러면 Funnel 로 나가서
 *   «다른 책» 을 보게 된다.
 */
const CDP = 'http://127.0.0.1:9222';
const OLD = process.argv[2] || 'http://127.0.0.1:8302/';
const NEW = process.argv[3] || 'http://127.0.0.1:3400/';
const API = process.argv[4] || 'http://127.0.0.1:8302';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function openTab(url) {
  const t = await (await fetch(`${CDP}/json/new?${url}`, { method: 'PUT' })).json();
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
  /* ★캐시를 끈다. 새 화면은 빌드마다 청크 이름이 바뀌는데, 크롬이 옛 index.html 을
     그대로 꺼내 쓰면 «고친 화면» 대신 «어제 화면» 을 대조하게 된다(2026-09-11 실측:
     out 은 page-78b2… 를 가리키는데 페이지는 page-c7ac… 를 들고 있었다). */
  await send('Network.enable');
  await send('Network.setCacheDisabled', { cacheDisabled: true });
  const ev = async (expr) =>
    (await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }))
      ?.result?.value;
  return {
    ev,
    goto: (u) => send('Page.navigate', { url: u }),
    close: async () => {
      await fetch(`${CDP}/json/close/${t.id}`);
      ws.close();
    },
  };
}

/** 숫자만 뽑는다 — 라벨·배지·공백은 두 화면이 다를 수 있고, 그건 지문이 아니다. */
const NUMS = `(s)=>String(s??'').match(/-?\\d+(?:\\.\\d+)?/g)||[]`;

/* ── 옛 화면: 자바스크립트가 스스로 접은 값 ─────────────────────────────── */
const OLD_TABS = `[...document.querySelectorAll('#seg button')].map(b=>({
  nm: b.childNodes[0].textContent.trim(),
  n: (b.querySelector('.c')?.textContent||'').replace(/,/g,'')
}))`;
const OLD_HEAT = `[...document.querySelectorAll('.hm tbody tr')].map(tr=>({
  row: tr.children[0].textContent.replace(/\\s+/g,' ').trim(),
  cells: [...tr.children].slice(1).map(td=>({
    v: td.childNodes[0]?.textContent.trim()||'',
    n: td.querySelector('.c')?.textContent.trim()||''
  }))
}))`;
const OLD_CRLIST = `[...document.querySelectorAll('#listBox .lr')].map(e=>({
  nm: e.querySelector('.t1')?.textContent.replace(/\\s+/g,' ').trim()||'',
  sub: e.querySelector('.t2')?.textContent.trim()||'',
  v: e.querySelector('.v')?.textContent.trim()||'',
  d: e.querySelector('.d')?.textContent.trim()||''
}))`;
const OLD_OB = `[...document.querySelectorAll('#obBox tbody tr')].slice(0,15).map(tr=>
  [...tr.children].map(td=>td.textContent.replace(/\\s+/g,' ').trim()))`;
const OLD_BONDS = `[...document.querySelectorAll('#listBox .lr')].slice(0,15).map(e=>({
  nm: e.querySelector('.t1 .nw')?.textContent.trim() || '',
  v: e.querySelector('.v')?.textContent.trim()||'',
  d: e.querySelector('.d')?.textContent.trim()||''
}))`;

/* ── 새 화면: 서버가 접어 준 값 ─────────────────────────────────────────── */
const NEW_TABS = `[...document.querySelectorAll('.kb-seg button')].map(b=>({
  nm: b.childNodes[0].textContent.trim(),
  n: (b.querySelector('.c')?.textContent||'').replace(/,/g,'')
}))`;
const NEW_HEAT = `[...document.querySelectorAll('.kb-hm tbody tr')].map(tr=>({
  row: tr.children[0].textContent.replace(/\\s+/g,' ').trim(),
  cells: [...tr.children].slice(1).map(td=>({
    v: td.childNodes[0]?.textContent.trim()||'',
    n: td.querySelector('.c')?.textContent.trim()||''
  }))
}))`;
const NEW_CRLIST = `[...document.querySelectorAll('.kb-li.cr')].map(e=>{
  const s=[...e.children].map(x=>x.textContent.replace(/\\s+/g,' ').trim());
  return {nm:s[0]||'', sub:s[1]||'', v:s[2]||'', d:s[3]||''};
})`;
const NEW_OB = `[...document.querySelectorAll('.kb-right .kb-tbl tbody tr')].slice(0,15).map(tr=>
  [...tr.children].map(td=>td.textContent.replace(/\\s+/g,' ').trim()))`;
/* ★새 화면의 종목 줄은 `.kb-li2` 다. `.kb-li` 로 잡으면 «관심»(axes) 목록이 먼저
   걸려 «22-8 사자 100억 19초» 같은 딴 줄을 세게 된다 — 첫 실행에서 그랬다. */
const NEW_BONDS = `[...document.querySelectorAll('.kb-li2')].slice(0,15).map(e=>{
  /* 칸 차례가 옛 화면과 다르다 — 새 화면은 [이름, 값, 부제, 민평대비] 이고
     옛 화면은 [이름·부제][값·민평대비] 로 묶여 있다. 이름·값·민평대비만 맞댄다. */
  const t=[...e.children].map(x=>x.textContent.replace(/\s+/g,' ').trim());
  return {nm:(t[0]||'').replace(/(지표|차기|레벨 미상|민평 [\d-]+).*$/,'').trim(),
          v:t[1]||'', d:t[3]||''};
})`;

function nums(x) {
  return (String(x ?? '').match(/-?\d+(?:\.\d+)?/g) || []).join(' ');
}

function diffRows(a, b, key) {
  const out = [];
  const n = Math.max(a.length, b.length);
  for (let i = 0; i < n; i++) {
    const x = nums(key(a[i]));
    const y = nums(key(b[i]));
    if (x !== y) out.push({ i, 옛: key(a[i]) ?? '(없음)', 새: key(b[i]) ?? '(없음)' });
  }
  return out;
}

const A = await openTab(OLD);
const Bt = await openTab(NEW);
await Bt.ev(`localStorage.setItem('kbond.base','${API}'); 1`);
await Bt.goto(NEW);
await sleep(9000);

const report = { 대조: [], 차이: {} };
const clickOld = (label) =>
  A.ev(`[...document.querySelectorAll('#seg button')].find(b=>b.textContent.trim().startsWith('${label}')).click();1`);
const clickNew = (label) =>
  Bt.ev(`[...document.querySelectorAll('.kb-seg button')].find(b=>b.textContent.trim().startsWith('${label}')).click();1`);

/* 1·2. 메인 — 탭 숫자와 히트맵 */
const tabsA = await A.ev(OLD_TABS);
const tabsB = await Bt.ev(NEW_TABS);
report.차이.탭숫자 = diffRows(tabsA, tabsB, (r) => (r ? `${r.nm} ${r.n}` : null));
const heatA = await A.ev(OLD_HEAT);
const heatB = await Bt.ev(NEW_HEAT);
report.차이.히트맵 = diffRows(heatA, heatB, (r) =>
  r ? `${r.row} ${r.cells.map((c) => `${c.v}/${c.n}`).join(' ')}` : null);

/* 3·4. 크레딧 */
await clickOld('크레딧');
await clickNew('크레딧');
await sleep(4000);
const crA = await A.ev(OLD_CRLIST);
const crB = await Bt.ev(NEW_CRLIST);
report.차이.크레딧분류 = diffRows(crA, crB, (r) => (r ? `${r.nm} ${r.sub} ${r.v} ${r.d}` : null));
const obA = await A.ev(OLD_OB);
const obB = await Bt.ev(NEW_OB);
report.차이.크레딧오퍼 = diffRows(obA, obB, (r) => (r ? r.join(' ') : null));

/* 5. 국고 */
await clickOld('국고');
await clickNew('국고');
await sleep(4000);
const kA = await A.ev(OLD_BONDS);
const kB = await Bt.ev(NEW_BONDS);
report.차이.국고종목 = diffRows(kA, kB, (r) => (r ? `${r.nm} ${r.v} ${r.d}` : null));

report.대조 = [
  ['탭 숫자', tabsA.length, tabsB.length],
  ['히트맵 행', heatA.length, heatB.length],
  ['크레딧 분류 줄', crA.length, crB.length],
  ['크레딧 오퍼 줄', obA.length, obB.length],
  ['국고 종목 줄', kA.length, kB.length],
];

console.log(JSON.stringify(report, null, 1));
await A.close();
await Bt.close();
