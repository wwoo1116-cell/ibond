/* 가드들이 소스를 훑을 때 쓰는 도구 — **한 벌**로.
 *
 * v1 패리티 레인 P2 (LANE-v1-parity-2026-08-20.md). v1 `guards/_source.ts`.
 *
 * ## 왜 모았나
 *
 * `stripComments` 가 여섯 가드에 각각 복사돼 있었고, **이미 갈려 있었다**
 * (2026-08-20 확인): 다섯은 뒤따라오는 주석까지 걷었고 하나(내가 쓴
 * `production-env`)는 줄 전체가 주석일 때만 걷었다. 갈렸다는 것 자체보다
 * 나쁜 것은, 그 차이를 **아무도 모른 채** 각 가드가 조금씩 다른 텍스트를 보고
 * 있었다는 사실이다.
 *
 * 주석을 걷는 이유는 하나다: 가드는 **동작하는 코드**를 검사해야 하고, 설명은
 * 동작이 아니다. 주석에 적힌 예시 색·예시 주소·옛 코드 조각 때문에 가드가
 * 터지면, 다음 사람은 가드를 고치는 대신 설명을 지운다.
 *
 * ## 함정 셋 (v1 이 적어 둔 것)
 *
 *   1. **URL 은 주석이 아니다.** `https://x` 의 `//` 를 걷으면 그 줄의 나머지가
 *      사라진다. `//` 앞 글자가 `:` 이면 건드리지 않는다.
 *   2. **주석 안의 따옴표가 코드를 삼키면 안 된다.** 문자열 파서를 쓰지 않고
 *      정규식으로 거는 이유이기도 하다 — 파서를 쓰면 짝이 안 맞는 따옴표
 *      하나에 파일 전체가 주석이 된다.
 *   3. **줄 번호가 살아남아야 한다.** 실패 문장이 "몇 번째 줄" 을 말하려면
 *      걷은 자리에 줄바꿈이 남아야 한다. 그래서 줄을 지우지 않고 **비운다**.
 */

import fs from 'node:fs';
import path from 'node:path';

/** 블록 주석과 줄 주석을 걷는다. 줄 수는 보존한다.
 *
 * 블록 주석은 여러 줄에 걸칠 수 있으므로 안의 줄바꿈을 그대로 남긴다 — 지우면
 * 그 아래 모든 실패가 잘못된 줄 번호를 말한다. */
export function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '))
    .replace(/(^|[^:])\/\/.*$/gm, '$1');
}

/** 디렉터리를 훑어 확장자가 맞는 파일 경로를 모은다. `node_modules` 와 빌드
 * 산출물은 건너뛴다 — 거기까지 훑으면 가드가 몇 분씩 걸린다. */
export function walk(dir: string, exts: readonly string[], out: string[] = []): string[] {
  for (const name of fs.readdirSync(dir)) {
    if (name === 'node_modules' || name === '.next' || name === '.git') continue;
    const full = path.join(dir, name);
    if (fs.statSync(full).isDirectory()) walk(full, exts, out);
    else if (exts.some((e) => full.endsWith(e))) out.push(full);
  }
  return out;
}
