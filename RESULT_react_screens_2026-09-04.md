# React 화면 셋 이식 + 지문 대조 (2026-09-04)

[OWNER 2026-09-04] 「남은 프론트도 일단 고치고 있자」 — 화면 셋을 다 옮기고 대조까지 했다.

## 1. 결론 — 지문 셋이 전부 맞다

같은 동결(20260903 11:00:00, T=39600)에서 **옛 화면의 자바스크립트 계산**과
**파이썬 계산**을 맞댔다. 브라우저 쪽은 페이지의 자기 함수(`bondRows`·`uncross`·
`bestOf`·`binOf`·`alive`)로 냈고, 파이썬 쪽은 `/api/view` 응답으로 냈다.

| 항목 | n | 지문 | 판정 |
|---|---|---|---|
| 종목 행(`bond_rows`) | 38 | `9622e1be5d81f87a` | **일치** |
| 호가 사다리(`ob_ladder`, 25-4) | 칸 3 | `527a8a1bbf73e033` | **일치** |
| 딜러 리더보드(`leaderboard`) | 120 | `7187a7ba33a8cba7` | **일치** |

사다리 지문에는 칸 값뿐 아니라 꼬리표까지 넣었다 —
`basis=amt|na=5|nb=6|a=500|b=600|fa=3.725|fb=3.730`. 막대 잣대(억이냐 건수냐)와
최우선까지 같아야 «같은 책» 이다.

★대조 전에 `SNAP.prev.ktb` 가 25종 실린 것을 확인했다. `load_prev` 가
백그라운드라 기동 직후에 재면 종목이 짧아 지문이 헛나온다(인계 문서 §C 경고 그대로).

★**09-03 지문 셋(`e79d9d5140e8ce1d` 등)은 이제 안 나온다.** 값이 틀린 게 아니라
오늘 파서를 고쳐 책이 옮겨간 것이다. 양쪽이 같이 움직여 **서로는 여전히 일치**한다.

## 2. 백엔드에 더한 계산 (화면에서 계산하지 않기 위해)

`/api/view` 가 안 내던 것을 `kbond_view.py` 로 옮겼다. 전부 화면 함수의
«계산» 절반만 떼어 온 것이고, 막대 폭·나이 칩·툴팁 문구는 화면에 남겼다.

| 함수 | 옮겨 온 곳 | 비고 |
|---|---|---|
| `ob_ladder` | `renderOb` | 빈 칸 격자를 **반복 덧셈**으로 채우는 것까지 같게 뒀다 |
| `dealer_cards` | `renderDeal` | 양면 먼저·신선한 순 정렬 그대로 |
| `swap_book` | `renderSwap` | 레벨은 신형−구형 **bp** 다. ×100 하지 않는다 |
| `cr_sel` · `cr_needs` | `crSel` · `crNeeds` | JS `indexOf` 의 **−1 의미**를 `_idx()` 로 맞췄다 |
| `pulse_stats` · `event_counts` | `renderPulse` · `renderEvents` | 어제 같은 시각 누적 대비 포함 |
| `curve_today` · `leaderboard` | `renderCurveToday` · `renderDealers` | 정렬 순서가 곧 화면이라 지문에 넣었다 |

API: `/api/view` 에 `code`·`agg` 추가, lane 에 `dyn` 추가.
스키마: `ObLadder`·`DealerCards`·`SwapBook`·`Pulse`·`Leaderboard`·`CurveTodayRow` 등
→ `openapi.json` → `api-types.d.ts` 기계 생성.

## 3. ★찾은 결함 셋 (전부 이번에 드러난 것)

### 3.1 `View` 타입이 통째로 `never` 였다

```ts
type Schemas = paths extends { [k: string]: unknown } ? … : never;
```

**인터페이스에는 암묵적 인덱스 시그니처가 없어** 이 조건이 항상 거짓이다. 기계로
뽑은 타입이 전부 버려지고 `View`·`BondRow`·`CreditBucket`·`Heat`·`Curve` 가 `never`
였다. 쓰는 곳이 없어 안 드러났을 뿐, 화면을 붙이는 순간 타입 안전망이 없었다.
직접 가리키도록 고쳤다.

### 3.2 `.kb-card` 는 설정 화면 전용인데 새 화면이 물려 썼다

`width: min(460px, 100%)` 라 세 화면의 모든 판이 460px 에 갇혔다. 세 컨테이너
안에서만 다시 정의했다(설정 화면은 그대로).

### 3.3 CSS 변수 이름이 실제와 달랐다 — 브라우저에서 실측

| 변수 | `:root` | 카드 위치 |
|---|---|---|
| `--sr-up` · `--sr-down` | 있음 | 있음 |
| `--color-bg` · `--color-fg` · `--color-fgMuted` · `--color-bgLine` | **없음** | 있음(주인 = `div.kbond`) |
| `--sr-card` · `--sr-page` | **없음** | **없음** |
| `--background` · `--line` · `--lineHeavy` | **없음** | **없음** |

CDS 는 팔레트를 ThemeProvider 요소에 인라인으로 뱉는다. `direction.css` 는 그걸
알고 `[data-sr-scheme]` 에 별칭을 선언하는데, `providers.tsx` 가 그 속성을
**`documentElement`(CDS 요소보다 위)** 에 붙여서 별칭이 죽어 있다.
새 CSS 는 `--color-*` 를 직접 쓴다. **기존 `.kb-app`·`.kb-bar` 규칙도 정의되지
않은 `--background`·`--lineHeavy` 를 참조하고 있다(대체값으로 버티는 중).**

## 4. 화면 (전부 실데이터로 눈으로 확인)

- **종목** — 좌 목록(지표·차기 배지, Δbp) / 중 요약·교체 / 우 사다리·딜러.
  25-4 에서 오퍼 3.725 < 비드 3.730, 매도 합 500억 5건 · 매수 합 600억 6건.
- **크레딧** — 분류 pill · 버킷(중앙 YTM·Δbp) · 커브 SVG(잔존×YTM + 민평선 224종) ·
  매수 니즈 31건 · 오퍼 227건(레벨 미상 7 을 따로 구획).
- **동향** — 맥박(칸 16·어제선) · 이벤트 180(종류 필터) · 커브 오늘 · 리더보드 292곳.

`tsc --noEmit` exit 0. 콘솔 오류 없음.

## 4.5 테마 결함 수리 + 시세·테이프 (같은 날 2차)

### 결함 — `data-sr-scheme` 가 잘못된 자리에 있었다

`providers.tsx` 가 그 속성을 `document.documentElement` 에 붙였는데, CDS 는
`--color-*` 를 **자기 ThemeProvider 래퍼에 인라인으로** 심는다. 커스텀 속성은
«선언된 자리» 에서 치환되므로, 조상인 html 에서 `--sr-card: var(--color-bg)` 는
빈 값으로 죽는다. `direction.css` 주석이 «그 div 는 ThemeProvider 의 **자식**» 이라고
적어 둔 그 자리가 비어 있었던 것이다.

수리: `PortalProvider` 안에 `div.kb-scheme-root[data-sr-scheme]` 를 두고
`display: contents` 로 상자를 안 만들게 했다. html 의 속성은 남겼다 —
`color-scheme` 은 UA 힌트라 문서 뿌리에 있어야 스크롤바가 따라온다.

실측 (같은 요소에서):

| | 수리 전 | 수리 후 |
|---|---|---|
| `--sr-card` | (없음) | 라이트 `rgb(255,255,255)` · 다크 `rgb(20,21,25)` |
| `--sr-page` | (없음) | 라이트 `rgb(238,240,243)` · 다크 `rgb(10,11,13)` |
| `.kb-app` 바탕 | (빈 값 — 투명) | 스킴대로 |

### 결함 — 없는 변수를 참조하고 있었다

`kbond.css` 의 `--background`·`--foreground`·`--line`·`--lineHeavy`·
`--backgroundElevation1` 계열은 **이 앱 어디에도 정의돼 있지 않았다**. 대체값이
있는 것은 그 값으로 버텼지만 `.kb-app` 의 바탕·글자색은 대체값조차 없어
다크에서 통째로 빈 채였다. 전부 `--color-*` 로 바꿨다.

### 면은 별칭으로

내가 처음에 `--color-bgAlternate`(페이지)·`--color-bg`(카드)로 못박았는데,
`direction.css` 는 **라이트와 다크에서 역할이 뒤집힌다**(다크는 페이지=`bg`,
카드=`bgElevation1`). 살아난 `--sr-page`·`--sr-card`·`--sr-control` 로 바꿨다.

### 시세 · 메시지 테이프

종목 화면 중앙의 빈자리를 채웠다.

- `px_series`(신규) — `drawPx` 의 계산 절반. 표본 절단과 **세로 범위**를 낸다.
  범위는 그리기가 아니라 규칙이라 서버 몫이다: [OWNER] 전일 민평이 정중앙.
  실측 25-10: 민평 3.790 → lo 3.7444 / hi 3.8356 (대칭) · 표본 611 · 활동 12칸.
- 메시지 테이프는 피드를 `code` 로 **고르는** 것뿐이라 화면에서 한다(접거나 세지
  않는다). `page.tsx` 가 이미 들고 있던 피드를 내려 준다.

## 5. 남은 것

★[2026-09-11] 1·2 는 닫혔다 — 히트맵과 등급 커브는 `Credit.tsx` 에 있고 `eslint`·
`eslint-config-next` 는 devDependencies 에 들어와 있다(`npm run lint` 가 돈다. 다만
`out/` 을 함께 훑어 빌드 산출물에서 오류 13개가 뜬다 — 소스는 깨끗하다).
3(전환)은 그대로 열려 있다. 같은 날 옛 화면에만 있던 셋을 마저 옮겼다 — 히트맵
«묵은 민평» 별표·«등급 무시» 토글·커브 x축 범위 토글, 그리고 크레딧 메시지 테이프.

1. 크레딧 커브의 히트맵·`mtx_group` 등급 커브 미표시.
2. **`eslint` 가 아예 설치돼 있지 않다** — `package.json` 에 `lint` 스크립트는 있는데
   devDependencies 에 `eslint`·`eslint-config-next` 가 없다. 고치려면 의존성을 더해야
   해서 오너 판단으로 남긴다(설치할지, 아니면 스크립트를 지울지).
3. 전환([3]단계)은 시작 안 했다 — Vercel 새 프로젝트·나란히 하루·오너 승인.

## 재현

```bash
# 백엔드(동결)
cd C:\Users\infomax\Projects\apps\kbond
set KBOND_REPLAY=20260903&& set KBOND_AT=11:00:00&& set KBOND_NO_MASK=1&& ^
  python -m uvicorn kbond_api:app --host 127.0.0.1 --port 8302
# 옛 화면(지문 대조용)
python kbond_live.py --replay 20260903 --at 11:00:00 --port 8305 --no-mask --viewer kbond_live.html
# 새 화면
cd ..\kbond-web && pnpm dev          # :3400, 설정에 http://127.0.0.1:8302
```
