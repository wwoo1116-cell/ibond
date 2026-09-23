/* 백엔드 주소가 정해지는 «단 한 곳».
 *
 * 배포 형태: 이 앱은 Vercel 이 배달하고, 책은 오너 PC 의 `kbond_api.py` 가 든다.
 * 그래서 데이터 요청은 Vercel 서버가 아니라 **보는 사람 브라우저** 가 다른 출처로 나간다.
 *
 * ★주소를 코드에 굽되(링크만 열면 뜨게), 저장된 값이 있으면 그것이 이긴다.
 *   토큰은 지금 꺼져 있다 [OWNER 2026-09-03 「토큰 빼고 Funnel 유지」] — 켜지면
 *   `?t=` 하나가 붙는 것뿐이라 여기 말고는 고칠 데가 없다.
 */
import type { paths } from './api-types';

const LSK = { base: 'kbond.base', tok: 'kbond.tok' } as const;

export const DEFAULT_API = 'https://e110430.tailc7b701.ts.net/kbond';

function read(key: string): string {
  try {
    return localStorage.getItem(key) ?? '';
  } catch {
    return ''; /* 사생활 모드 — 기본값으로 간다 */
  }
}

export function apiBase(): string {
  const saved = read(LSK.base).replace(/\/+$/, '');
  return saved || DEFAULT_API;
}

export function apiToken(): string {
  return read(LSK.tok);
}

export function setApi(base: string, tok: string) {
  try {
    localStorage.setItem(LSK.base, base.replace(/\/+$/, ''));
    localStorage.setItem(LSK.tok, tok);
  } catch {
    /* 저장 못 해도 이번 세션은 돈다 */
  }
}

export function clearApi() {
  try {
    localStorage.removeItem(LSK.base);
    localStorage.removeItem(LSK.tok);
  } catch {
    /* 무시 */
  }
}

/** 경로 + 쿼리 -> 최종 URL. 토큰은 여기서만 붙는다.
 *  ★쿼리로 받는 이유: EventSource 는 커스텀 헤더를 못 싣는다. 네 요청이 전부
 *    헤더 없는 단순 GET 이 되어 프리플라이트도 없다. */
export function url(path: string, qs?: Record<string, string | number | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(qs ?? {})) {
    if (v !== undefined && v !== null && v !== '') q.set(k, String(v));
  }
  const t = apiToken();
  if (t) q.set('t', t);
  const s = q.toString();
  return apiBase() + path + (s ? `?${s}` : '');
}

/** 401 은 «토큰이 바뀌었다» 는 뜻이다 — 저장값을 버리고 다시 묻게 한다. */
export class Unauthorized extends Error {
  constructor() {
    super('401');
    this.name = 'Unauthorized';
  }
}

export async function get<T>(path: string, qs?: Record<string, string | number | undefined>) {
  const r = await fetch(url(path, qs), { cache: 'no-store' });
  if (r.status === 401) {
    clearApi();
    throw new Unauthorized();
  }
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return (await r.json()) as T;
}

/* ── 타입은 OpenAPI 에서 기계로 뽑은 것을 쓴다 ────────────────────────────
 * 손으로 다시 적으면 «적히지 않은 계약을 두 번 베끼는» 셈이 된다. 백엔드에서
 *   python -c "import json; from kbond_api import app; ..." > openapi.json
 *   npx openapi-typescript@7 openapi.json -o src/lib/api-types.d.ts
 * 로 다시 뽑는다. */
/* ★2026-09-04: 여기 `paths extends { [k: string]: unknown } ? … : never` 가 있었는데
 *   **인터페이스에는 암묵적 인덱스 시그니처가 없어** 그 조건이 항상 거짓이었다.
 *   그래서 `View` 가 통째로 `never` 였고, 파생 타입(BondRow·CreditBucket…)도 전부
 *   `never` 였다. 쓰는 곳이 없어 여태 안 드러났을 뿐이다 — 직접 가리킨다. */
export type View = paths['/api/view']['get']['responses'][200]['content']['application/json'];
export type BondRow = NonNullable<View['rows']>[number];
export type CreditBucket = NonNullable<View['buckets']>[number];
export type Heat = View['heat'];
export type Curve = NonNullable<View['curve']>;
export type FeedPage =
  paths['/feed.json']['get']['responses'][200]['content']['application/json'];
export type FeedRow = FeedPage['feed'][number];

export type Lane = 'ktb' | 'msb' | 'nhb' | 'cr' | 'dyn';
export type TtlMode = 'def' | 'half' | 'inf';

/** `code` 를 주면 그 종목의 사다리·딜러·교체까지 서버가 같이 낸다(화면은 안 접는다). */
export const getView = (
  lane: Lane,
  ttl: TtlMode,
  cls?: string,
  rt?: string,
  code?: string,
  agg?: number,
) => get<View>('/api/view', { lane, ttl, cls, rt, code, agg: agg || undefined });

export const getFeed = (since: number, limit = 3000) =>
  get<FeedPage>('/feed.json', { since, limit });

/** 살아 있는지. 문턱 밖이라 토큰이 없어도 200 이 온다(대신 {ok:true} 만). */
export const getHealth = () =>
  get<{ ok: boolean; ver?: number; px_settle?: string; px_assume_quarterly?: boolean }>(
    '/health',
  );
