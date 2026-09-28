/**
 * 첫 화면이 실제로 받는 바이트를 잰다. [2026-09-28 경량화 레인에서 옮겨 심음]
 *
 * 왜 도구로 남기나
 *   09-28 에 첫 화면을 3.13MB → 1.57MB 로 줄였다. 그 뒤로 이 앱에 무엇을 더하든
 *   «메인 첫 화면은 안 무거워졌는가» 를 물어야 하는데, 디스크의 `out` 크기로는
 *   답이 안 나온다 — 브라우저는 화면에 필요한 조각만 받고(글꼴 96장 중 18장),
 *   지연 로드한 청크는 그 탭을 열 때만 받는다. **받은 바이트**만이 답이다.
 *
 * 무엇을 세나
 *   1) 메인 첫 화면의 종류별 합계(js·css·font·html·api)
 *   2) 탭을 하나 열었을 때 «더» 받은 바이트 — 지연 로드가 제대로 갈렸는지
 *
 * 쓰는 법
 *   node measure_load.mjs [화면URL] [API] [탭]
 *     node measure_load.mjs http://127.0.0.1:3400/ http://127.0.0.1:8302 국고
 */
const CDP = 'http://127.0.0.1:9222';
const URL_ = process.argv[2] || 'http://127.0.0.1:3400/';
const API = process.argv[3] || 'http://127.0.0.1:8302';
const TAB = process.argv[4] || '국고';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const t = await (await fetch(`${CDP}/json/new?about:blank`, { method: 'PUT' })).json();
const ws = new WebSocket(t.webSocketDebuggerUrl);
let id = 0;
const waits = new Map();
const send = (method, params = {}) =>
  new Promise((res) => {
    const i = ++id;
    waits.set(i, res);
    ws.send(JSON.stringify({ id: i, method, params }));
  });

const reqs = new Map();
ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if (m.id && waits.has(m.id)) { waits.get(m.id)(m.result); waits.delete(m.id); return; }
  if (m.method === 'Network.requestWillBeSent') reqs.set(m.params.requestId, { url: m.params.request.url, enc: 0, mime: '', status: 0 });
  if (m.method === 'Network.responseReceived') {
    const r = reqs.get(m.params.requestId);
    if (r) { r.mime = m.params.response.mimeType; r.status = m.params.response.status; }
  }
  if (m.method === 'Network.loadingFinished') {
    const r = reqs.get(m.params.requestId);
    if (r) r.enc = m.params.encodedDataLength;
  }
};
await new Promise((r) => (ws.onopen = r));
await send('Network.enable');
await send('Network.setCacheDisabled', { cacheDisabled: true });
await send('Page.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1500, height: 1100, deviceScaleFactor: 1, mobile: false });
const ev = async (expr) =>
  (await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }))?.result?.value;

await send('Page.navigate', { url: URL_ });
await sleep(1500);
await ev(`localStorage.setItem('kbond.base', ${JSON.stringify(API)}); localStorage.removeItem('kbond.tok'); 1`);

/** 한 구간의 바이트를 종류별로 접는다. */
const kindOf = (r) => {
  const u = r.url.split('?')[0];
  if (/\.woff2?$/.test(u)) return 'font';
  if (/\.js$/.test(u)) return 'js';
  if (/\.css$/.test(u)) return 'css';
  if (/\/(feed\.json|api\/view|health|events|book\.json)/.test(u)) return 'api';
  if (/\.html?$/.test(u) || u.endsWith('/')) return 'html';
  return 'other';
};
const fold = (rows) => {
  const by = {};
  for (const r of rows) {
    const k = kindOf(r);
    by[k] = by[k] || { n: 0, b: 0 };
    by[k].n++;
    by[k].b += r.enc;
  }
  return by;
};
const show = (title, rows) => {
  const by = fold(rows);
  const statik = ['font', 'js', 'css', 'html'].reduce((s, k) => s + (by[k]?.b || 0), 0);
  console.log(`\n── ${title}`);
  for (const k of Object.keys(by).sort()) console.log(`   ${k.padEnd(6)} ${String(by[k].n).padStart(3)}건 ${String(by[k].b).padStart(9)}B`);
  console.log(`   ${'정적'.padEnd(5)} (font+js+css+html) ${String(statik).padStart(9)}B`);
  return statik;
};

reqs.clear();
await send('Page.navigate', { url: URL_ });
await sleep(9000);
const first = [...reqs.values()].filter((r) => r.status);
const firstStatic = show(`메인 첫 화면 ${URL_}`, first);

reqs.clear();
const clicked = await ev(
  `(()=>{const b=[...document.querySelectorAll('.kb-seg button')].find(x=>x.textContent.includes(${JSON.stringify(TAB)}));
    if(!b) return 'no-tab'; b.click(); return 'ok';})()`,
);
await sleep(9000);
const after = [...reqs.values()].filter((r) => r.status);
const tabStatic = show(`«${TAB}» 탭을 열고 더 받은 것 (${clicked})`, after);
const js = after.filter((r) => kindOf(r) === 'js');
if (js.length) {
  console.log('   새 JS:');
  for (const r of js.sort((a, b) => b.enc - a.enc)) console.log(`       ${String(r.enc).padStart(8)}B  ${r.url.split('/').pop()}`);
}
console.log(`\n요약: 첫 화면 정적 ${firstStatic}B · «${TAB}» 추가 정적 ${tabStatic}B`);
await fetch(`${CDP}/json/close/${t.id}`);
ws.close();
