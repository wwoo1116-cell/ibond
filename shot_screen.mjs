/**
 * 새 화면 한 탭을 헤드리스 크롬으로 찍는다. [2026-09-15]
 *
 * 왜 도구로 남기나
 *   **표현 계층은 verify_v4 도 compare_screens 도 안 덮는다.** v11 의 히트맵 칸 키(늘 비어
 *   있었다)와 v12 의 사다리 점 색(이 테마에 없는 토큰이라 투명)은 둘 다 «눈으로만» 잡혔다.
 *   compare_screens 는 두 화면이 «같은 수» 를 말하는지 세지, 새 화면에만 있는 칸이 제대로
 *   그려지는지는 아무도 안 본다. 그 자리를 이 스크립트가 메운다.
 *
 * 쓰는 법
 *   1) 동결 리플레이 백엔드를 띄운다(판정은 동결로만 — 장중 실황은 폴링 시차가 낀다):
 *        set KBOND_REPLAY=20260903&& set KBOND_AT=15:30:00&& ^
 *          python -X utf8 -m uvicorn kbond_api:app --host 127.0.0.1 --port 8303
 *   2) 새 화면 정적 빌드를 :3400 으로 낸다(그 포트가 CORS 허용 목록에 있다):
 *        cd ..\kbond-web && npm run build && python -m http.server 3400 --directory out
 *   3) 헤드리스 크롬을 디버깅 포트로 띄운다:
 *        chrome --headless=new --remote-debugging-port=9222 --user-data-dir=<임시> about:blank
 *   4) node shot_screen.mjs [화면URL] [API] [출력.png] [탭이름] [고를 종목]
 *        node shot_screen.mjs http://127.0.0.1:3400/ http://127.0.0.1:8303 dyn.png 동향
 *        node shot_screen.mjs http://127.0.0.1:3400/ http://127.0.0.1:8303 ob.png 국고 26-7
 *   ★사다리·시세·딜러는 종목을 골라야 나온다. 안 고르면 목록 첫 줄이 잡히는데 그게 한쪽
 *     호가만 있는 종목이면 «바램 단계가 안 보이는» 그림을 찍게 된다.
 *
 * 찍은 그림 말고 **stdout 의 kv 줄** 도 보라 — 칸 라벨과 값이 한 줄로 나오므로
 * 「두 줄로 접혀 칸 높이가 어긋났다」 같은 것이 글자로도 잡힌다.
 *
 * ⚠새 화면은 저장된 주소가 코드에 구운 주소를 이긴다(`api.ts`). 그래서 localStorage 에
 *   API 를 먼저 박고 다시 연다 — 안 그러면 Funnel 로 나가서 «다른 책» 을 찍는다.
 */
import { writeFileSync } from 'node:fs';

const CDP = 'http://127.0.0.1:9222';
const URL_ = process.argv[2] || 'http://127.0.0.1:3400/';
const API = process.argv[3] || 'http://127.0.0.1:8303';
const OUT = process.argv[4] || 'screen.png';
const TAB = process.argv[5] || '동향';
const PICK = process.argv[6] || '';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

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
/* 캐시를 끈다 — 빌드마다 청크 이름이 바뀌는데 크롬이 옛 index.html 을 꺼내 쓰면
   «고친 화면» 대신 «어제 화면» 을 찍는다(compare_screens 와 같은 이유). */
await send('Network.enable');
await send('Network.setCacheDisabled', { cacheDisabled: true });
await send('Emulation.setDeviceMetricsOverride', {
  width: 1500, height: 1100, deviceScaleFactor: 1, mobile: false,
});
const ev = async (expr) =>
  (await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }))
    ?.result?.value;

await sleep(1500);
await ev(`localStorage.setItem('kbond.base', ${JSON.stringify(API)}); localStorage.removeItem('kbond.tok'); 'ok'`);
await send('Page.navigate', { url: URL_ });
await sleep(4000);
const clicked = await ev(
  `(()=>{const b=[...document.querySelectorAll('.kb-seg button')]
     .find(x=>x.textContent.includes(${JSON.stringify(TAB)}));
   if(!b) return 'no-tab'; b.click(); return 'clicked';})()`,
);
console.log('탭', TAB, clicked);
/* 첫 폴링이 5초라 그것보다 넉넉히 기다린다(빈 카드를 찍으면 «없는 것» 처럼 보인다). */
await sleep(7000);
if (PICK) {
  const got = await ev(
    `(()=>{const r=[...document.querySelectorAll('.kb-li2')]
       .find(x=>(x.querySelector('.nm')||x).textContent.trim().startsWith(${JSON.stringify(PICK)}));
     if(!r) return 'no-row'; r.click(); return 'picked';})()`,
  );
  console.log('종목', PICK, got);
  await sleep(6000);
}
console.log('kv:', await ev(
  `[...document.querySelectorAll('.kb-kvc')].map(e=>e.textContent.replace(/\\s+/g,' ').trim()).join(' | ')`,
));
console.log('표:', await ev(
  `[...document.querySelectorAll('.kb-tbl thead')].map(h=>[...h.querySelectorAll('th')].map(x=>x.textContent.trim()).join(',')).join(' || ')`,
));
const shot = await send('Page.captureScreenshot', { format: 'png' });
writeFileSync(OUT, Buffer.from(shot.data, 'base64'));
console.log('저장', OUT);
await fetch(`${CDP}/json/close/${t.id}`);
ws.close();
