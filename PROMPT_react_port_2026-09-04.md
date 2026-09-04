# K-Bond 프롬프트 — React 이식 마무리와 전환 (2026-09-04)

아래 코드블록을 그대로 새 세션에 붙여 넣는다. 그 밑의 «근거» 절은 **이미 재 놓은 것**이라
받는 세션은 다시 재지 않고 인용하면 된다.

**지금 프로덕션은 멀쩡히 돌고 있다. 이 레인은 «옆에 짓는» 일이지 «고치는» 일이 아니다.**

---

## 붙여 넣을 프롬프트

```
K-Bond 레인을 이어서 한다. React 이식을 마무리하고 전환한다.

먼저 읽을 것 (순서대로):
- C:\Users\infomax\Projects\apps\kbond\PROMPT_react_port_2026-09-04.md 의 «근거» 절
  — 주소·포트·검증 명령·함정이 전부 여기 있다. 다시 재지 말고 인용하라.
- C:\Users\infomax\Projects\apps\kbond\RESULT_backend_fastapi_2026-09-03.md — 계산이 어디로 갔나
- C:\Users\infomax\Projects\apps\sauron-v2\DESIGN.md §1 — 디자인 문법의 근거(측정)
- C:\Users\infomax\Projects\apps\kbond\KBOND_LANE_PROMPT.md §1 DECIDED — 다시 열지 않는다

## 지금 무엇이 돌고 있나

  트레이더가 보는 것 : https://ibond-theta.vercel.app   (HTML 판, 피드백 받는 중)
        └─ 데이터 ──> https://e110430.tailc7b701.ts.net/kbond  (Tailscale Funnel)
                        └─> 127.0.0.1:8301  kbond_live.py  (예약태스크 KBondLive 평일 08:20)

  새 백엔드 : kbond_api.py (FastAPI)  — 수동 실행, :8302. 같은 엔진을 부른다.
  새 화면   : Projects\apps\kbond-web (Next.js + CDS) — 수동 실행, :3400. 메인 피드만 있다.

**프로덕션(:8301)과 Vercel 의 HTML 판은 이 레인이 끝날 때까지 건드리지 않는다.**
트레이더가 그걸 보고 있고, [OWNER] 가 «안정적으로 완성되는 것» 을 우선한다고 했다.

## 오너가 정한 것 (DECIDED — 다시 열지 않는다)

[OWNER 2026-09-03] 「계산과 집계는 서버, 화면은 서버가 계산한 값을 쓴다」
[OWNER 2026-09-03] 「디자인 문법은 v2와 동일하게」 → CDS + sauronTheme. §D 에 실측 규칙.
[OWNER 2026-09-03] 「토큰 빼고 Funnel 유지」 — 위험을 알린 뒤의 결정이다. 되돌리지 말 것.
[OWNER 2026-09-03] 「딜러이름이랑 번호는 일단 XXX로」 → 가림은 켜 둔다(H01-2·K001).
[OWNER 2026-09-03] 「안정적으로 완성되는 걸 중요시」 → 전환은 나란히 놓고 비교한 뒤에.

## 오너 대기 (막지 말고 기본값으로 가되 보고에 적을 것)

- ibond 리포가 **public** 이다. 닫을지 물었고 답을 못 받았다. 기본값: 그대로 둔다.
  (닫아도 백엔드는 안 지켜진다 — 근거 §E)
- 가림 라벨을 «완전히 하나로 뭉갤지»(지금은 H01-2 처럼 구분된다). 기본값: 지금대로.
- weak 체결 귀속(71.6%) 되살릴지. 기본값: 뺀 채로.
- 대량 이벤트 문턱 300억. 기본값: 유지.

## [1] 화면 이식 — **셋 다 옮겼다(2026-09-04)**

종목·크레딧·동향 세 화면을 옮기고 지문 셋을 맞댔다.
상세는 `RESULT_react_screens_2026-09-04.md`. 남은 것은 시세 캔버스·메시지 테이프와
[3] 전환이다. 아래는 당시 사양이다.

<!-- 당시 사양 -->
## [1] 화면 이식 — 셋을 옮긴다

지금 kbond-web 에는 «메인 피드» 하나뿐이다. HTML 판(kbond_live.html)에 있는 나머지를 옮긴다.
순서는 트레이더가 많이 보는 것부터다.

  (a) 종목 화면 — 좌 목록 / 중 요약·시세 / 우 3열 호가창 · 딜러 카드
  (b) 크레딧 — 분류 pill · 버킷 목록 · 커브(잔존×YTM) · 매수 니즈
  (c) 동향 — 시장 맥박 · 이벤트 · 커브 오늘 · 딜러 리더보드

**계산은 하지 않는다.** `/api/view?lane=&ttl=&cls=&rt=` 가 이미 낸다:
  rows(종목 한 줄: 최우선·mid·민평대비·어제) · buckets(종별×등급 중앙값) ·
  heat(히트맵 칸) · curve(점과 기준선) · counts(탭 숫자)
화면에서 uncross·중앙값·활성 필터를 다시 짜면 규칙이 두 벌이 되고 언젠가 갈라진다.

`/api/view` 에 없는 것이 필요하면 **화면이 아니라 `kbond_view.py` 에 더한다.** 그리고
근거 §C 의 지문 대조를 그 항목에도 한 번 돌린다.

캔버스 그림(시세·커브·맥박)은 HTML 판의 함수를 그대로 옮겨도 된다 — 그건 «계산» 이 아니라
«그리기» 다. 다만 좌표 계산에 쓰는 값은 서버가 준 것을 쓴다.

## [2] 대조 — 옮긴 화면이 옛 화면과 같은 값을 내는가

한 화면을 옮길 때마다 근거 §C 의 방법으로 지문을 맞댄다. **눈으로 비슷하다는 것은 대조가
아니다.** 옛 HTML(:8301)과 새 React(:3400)를 같은 동결 리플레이에 붙이고,
같은 항목을 문자열로 만들어 정렬·SHA-1. 숫자는 반드시 `.toFixed(6)` / `f"{v:.6f}"` 로 고정한다
(안 하면 JS `-3` 대 파이썬 `-3.0` 으로 어긋난다 — 실제로 겪었다).

## [3] 전환

셋이 다 옮겨지고 대조가 서면:
  1. kbond-web 을 Vercel 에 **새 프로젝트로** 올린다(ibond 는 그대로 둔다).
  2. 두 주소를 나란히 놓고 하루 돌린다.
  3. [OWNER] 승인을 받고 ibond 를 교체하거나 주소를 바꾼다.
  4. 백엔드는 그때 :8301 을 kbond_api.py 로 갈아탄다 — 예약태스크의 실행 줄을
     `python -m uvicorn kbond_api:app --host 127.0.0.1 --port 8301` 로.
     그 전에 `verify_v4.py --port 8302` 가 [A]~[H] 전건 통과인지 다시 본다.

## [4] 남은 미완 (이 레인 밖이지만 알고 있을 것)

- 크레딧 TTL 의 «레벨 지속» 미측정(국고만 쟀다 — RESULT_ttl_review.md).
- 지방/첨가물 종목 확정 불가(마스터가 없다). 섹터와 사다리 칸까지만.
- 분리채 민평이 우리 DB 대비 +5.6bp 계통 차 — 문면 민평만 쓴다.
- infomax.matrix_* 8장이 2026-01-23 에서 멈춰 있다(지방채 등급 커브가 그것뿐이다).

## 하지 말 것

- 프로덕션 :8301 을 죽이지 말 것. Vercel 의 ibond 를 갈아엎지 말 것.
- Book 엔진·파서(kbond_live.py 의 Book, parse_kbond_logs.py)를 건드리지 말 것.
  이 레인은 화면과 껍데기다.
- 화면에서 계산하지 말 것(위 [1]).
- 색을 hex 로 박지 말 것 — CDS 토큰이나 theme/direction.css 의 변수를 참조한다(v2 규율).
- dev 서버가 도는 중에 `pnpm build` 를 돌리지 말 것 — `.next` 를 덮어써 500 이 난다(겪었다).
- 통째 재작성 금지. exact-match 치환만.

## 보고

바뀐 파일마다 «어느 함수에 무엇을» + 대조 지문 + 검증 로그 + 캡처.
못 한 것은 못 했다고 적는다. «잘 도는 것처럼 보인다»와 «원본과 대조했다»는 다르다.
```

---

## 근거 (2026-09-03 세션이 잰 것 — 받는 세션은 인용만)

### A. 지금 있는 것 · 어디서 도나

| | 무엇 | 어디 | 어떻게 |
|---|---|---|---|
| 프로덕션 백엔드 | `kbond_live.py` | `127.0.0.1:8301` | 예약태스크 `KBondLive` 평일 08:20 (pythonw) |
| 새 백엔드 | `kbond_api.py` (FastAPI) | `:8302` | `python -m uvicorn kbond_api:app --host 127.0.0.1 --port 8302` |
| HTML 화면 | `kbond_live.html` | `:8301/` · Vercel | 트레이더가 보는 것 |
| React 화면 | `apps/kbond-web` | `:3400` | `node node_modules/next/dist/bin/next dev -p 3400` |
| 공개 주소 | Vercel | `https://ibond-theta.vercel.app` | ★접미사 없는 `ibond.vercel.app` 은 **남의 것** |
| 백엔드 공개 | Tailscale Funnel | `https://e110430.tailc7b701.ts.net/kbond` | `/`→8100 · `/v2`→8200 은 v2 것, 건드리지 말 것 |
| 리포 | `wwoo1116-cell/ibond` | GitHub **public** | 화면(HTML)만 올라간다 |
| 일간 배치 | `kbond_daily_update.py` | — | 예약태스크 `KBondDailyUpdate` 평일 16:30 |

### B. 계산이 어디로 갔나 (`RESULT_backend_fastapi_2026-09-03.md`)

`kbond_view.py` 가 화면이 하던 계산의 파이썬 판이다. 함수 이름이 HTML 의 것과 같다:
`uncross` · `best_of` · `med` · `bond_rows` · `cr_buckets` · `heat_cells` · `curve_points` ·
`cat_counts` · `mtx_group`. **옮기면서 «더 낫게» 고치지 않았다** — 다르면 대조가 깨지고
그 순간 어느 쪽이 맞는지 아무도 모른다.

`kbond_live.start_engine()` 이 엔진의 단 하나의 기동 경로다. 옛 판과 FastAPI 판이 같은 것을 부른다.

전송량(gzip): `/book.json` 61KB → `/api/view?lane=ktb` **2.2KB**.

### C. 대조 방법 — 이대로 하면 된다

브라우저(옛 화면)와 파이썬(새 계산)을 같은 동결 스냅샷에 붙이고 지문을 맞댄다.

```
# 1. 동결 리플레이를 띄운다 (가림 끔 — 라벨 번호가 서버마다 다를 수 있다)
python replay_verify.py 20260903 13:00:00 8305 --keep

# 2. 파이썬 쪽 지문
N = lambda v: "None" if v is None else f"{float(v):.6f}"
items = [f"{r['c']}~{N(r['mid'])}~{N(r['fa'] and r['fa']['y'])}~…" for r in rows]
hashlib.sha1("|".join(sorted(items)).encode()).hexdigest()[:16]

# 3. 브라우저 쪽 지문 (crypto.subtle.digest('SHA-1', …)) — 같은 규칙으로
```

> ### ★정정 (2026-09-04) — 아래 지문 셋은 이제 안 나온다
>
> 오늘 파서를 고쳐 책이 옮겨갔다(BondName·Position·QuoteRaw). 값이 틀린 것이
> 아니라 기준이 바뀐 것이고, 양쪽이 같이 움직여 **서로는 여전히 일치한다**.
> 새 기준은 `RESULT_react_screens_2026-09-04.md` §1 — 동결 **20260903 11:00:00(T=39600)**:
>
> | 항목 | n | 지문 |
> |---|---|---|
> | 종목 행 | 38 | `9622e1be5d81f87a` |
> | 호가 사다리(25-4) | 3 | `527a8a1bbf73e033` |
> | 딜러 리더보드 | 120 | `7187a7ba33a8cba7` |
>
> ★또 하나: 13:00 동결은 **국고 호가가 11:43 에 끊겨** TTL 30분 밖이라 사다리가
> 통째로 빈다. 사다리를 재려면 11:00 쪽을 쓸 것.

2026-09-03 13:00 동결에서 **전부 일치**했다:

| 항목 | n | 지문 |
|---|---|---|
| 국고 행 | 32 | `e79d9d5140e8ce1d` (어제 책 실린 뒤) |
| 크레딧 버킷 | 15 | `1107909c94047728` |
| 히트맵 칸 | 35 | `85eff12c9fa52a6d` |

★**숫자 표기를 먼저 못 박을 것.** 처음엔 어긋났는데 값이 아니라 표기 차이였다 —
JS `String(-3)`=`-3` 대 파이썬 `str(-3.0)`=`-3.0`.

★**대조는 «어제 책이 실린 뒤» 에 한다.** `load_prev` 가 백그라운드라 기동 직후 몇 초는
종목 목록이 짧다(32행이어야 할 것이 14행으로 나왔다).

### D. 디자인 문법 = v2 (`sauron-v2/DESIGN.md`, 실측)

`apps/kbond-web/src/theme/` 에 v2 것을 **복사해 두었다**(테마 id 만 `kbond`).

- Coinbase CDS(`@coinbase/cds-web`) + `sauronTheme`(defaultTheme 얇은 파생)
- 폰트 **Pretendard SR** 자체호스팅(`public/fonts/`). ★`local()` 없이 — 이 데스크에
  Pretendard 가 없어 옛 스택이 조용히 Malgun 으로 떨어진 실측 사고가 있다(굵기도 뭉개졌다)
- **굵기 두 단계 400/600**, 13px `legal` 만 500 [OWNER 2026-08-14 확정, 다시 묻지 말 것]
- 행 높이 **48** — 가상화가 이 값으로 스페이서를 계산한다. `space['1']=6` 이 그것을 맞춘다
- 방향색은 CDS 슬롯이 아니라 `theme/direction.css`(CDS 의 `fgPositive`/`fgNegative` 는
  이 시장과 반대다 — v2 소스에서 그 둘의 참조가 0회)
- 방향색은 토스증권 실측 `#de2b39`(상승) / `#2272eb`(하락). **hex 는 그 파일에만 있다**
- `bgAlternate` 에 부호 숫자를 올리지 말 것(대비 4.19:1 로 기준 미달 — v2 실측)
- `ThemeProvider` 하나, 중첩·라우트별 덮어쓰기 금지

★**CDS 의 실제 prop 이름**(내가 다섯 번 틀렸다):

| 내가 쓴 것 | 실제 |
|---|---|
| `paddingHorizontal` / `paddingVertical` | `paddingX` / `paddingY` |
| `<Text variant="…">` | `<Text font="…">` |
| `color="foregroundMuted"` | `color="fgMuted"` |
| `<Button onPress compact>` | `<Button onClick size="xs">` |
| `<TextInput onChangeText>` | `<TextInput onChange={e => …}>` |
| `background="bg"` | **없다.** v2 소스에 `background=` 가 0회 — CSS 로 칠한다 |

★CDS 의 Box/Stack 은 기본이 flex 라, 세로 목록은 CSS 로 `flex-direction: column` 을
못 박지 않으면 **행이 가로로 흐른다**(겪었다).

### E. 문턱과 노출 (`RESULT_audit_tailscale_2026-09-03.md`)

- **토큰 없음** [OWNER 결정]. 남은 문턱은 CORS 하나뿐이고 그건 **브라우저만** 막는다.
  `curl` 로는 주소를 아는 누구나 책 전체를 받는다. 되돌리려면 사용자 환경변수
  `KBOND_TOKEN` 을 넣고 `KBondLive` 를 재기동하면 된다(코드는 그대로 있다).
- **리포를 닫아도 백엔드는 안 지켜진다** — Vercel 배포는 리포 공개 여부와 무관하게 열리고,
  화면 소스에 `DEFAULT_API` 가 들어 있다. 제안했던 대안: 토큰을 켜고 화면이 `?t=` 를 읽어
  저장하게 하기(링크 한 줄로 편의는 같고 주소만 아는 사람은 401).
- 가림은 **책에 넣을 때** 한다(출력 직전이 아니다). `verify_v4.py` 의 [H] 절이
  전화번호꼴 0 · 실명 노출 0 을 본다. 자리마다 잣대가 다르다:
  `d·bk·h·k` 는 부분 일치도 누출, `n`(종목 이름)은 완전 일치만, `raw` 는 전화번호만.
- CORS 정규식은 **하이픈 필수**(`ibond-[a-z0-9-]+`). 아니면 남의 `ibond.vercel.app` 을 문다.
- gzip 은 넣어 두었다(`/book.json` 809→93KB).

### F. 검증 — 이 셋이 기준이다

```
python -m pytest test_frac.py test_cors_token.py -q     # 55건 (끝전 24 · 문턱 31)
python replay_verify.py 20260903 13:00:00 8305   # 동결 리플레이 + verify [A]~[H]
python verify_v4.py --port 8301 --day 20260903          # 프로덕션 라이브
```

★**verify 뒤에 서버 로그의 `[feed 오류]` 건수를 «재기동 시각 이후» 로 셀 것.**
예외를 삼키는 루프 밑에 새 코드를 넣으면 [A]~[E] 가 전부 통과하면서 크레딧 호가 1,824건이
통째로 빠질 수 있다(실제로 겪었고, 새로 만든 [F4b] 가 잡았다).

`verify_v4.py` 절 목록: [A] 체결 테이프 · [B] 국민주택 · [C] 사다리 불변식 · [C2] 민평에 ·
[D] 피드 · [E] 교체·내재 · [F] 체결 귀속 · [F2] 끝전 · [G] 맥박·딜러·이벤트 · [H] 가림.

### G. 이 레인에서 데인 것 (되풀이하지 말 것)

1. **패치 스크립트가 자기가 넣은 코드를 다시 잘랐다.** 새 함수를 먼저 삽입하고 옛 본문을
   «`ref = {...}` 부터» 잘랐더니 `s.index()` 가 새 쪽을 먼저 찾아 `main()` 이 통째로 사라졌다.
   **먼저 잘라내고 그다음에 넣는다.**
2. **토큰 검사가 HTML 까지 막아 로컬 화면이 401 이었다.** 비밀은 데이터이지 화면이 아니다 —
   `/` 와 `/health` 는 문턱 밖.
3. **피드 행의 `k` 는 이미 «메시지 종류» 였다.** 딜러키를 같은 이름으로 넣어 종류가 덮였고
   verify D4 가 3,000건 실패로 잡았다 → `bk`.
4. **크레딧 엔트리에 `"s"` 가 없어** `_after_quote` 가 KeyError 를 냈고, feed 의 try/except 가
   삼켜 호가 1,824건이 조용히 빠졌다.
5. **dev 서버가 도는 중에 프로덕션 빌드**를 돌려 `.next` 가 깨지고 화면이 500 을 냈다.
6. `pnpm` 이 스크립트 전에 의존성을 확인하는데 `sharp` 빌드 스크립트 경고가 종료 코드를
   1로 만든다 → `pnpm approve-builds --all` 한 번.
7. **브라우저의 첫 연결만 8초+ 걸린다**(Funnel). curl 은 처음부터 30ms — 이것 때문에
   «막혔다» 고 오판할 뻔했다.

### H. 동시 세션 주의 (2026-09-03 17:00 기준)

`infomax-73` 이 «미해석» 레인을 돌고 있다 — `PROMPT_unparsed_2026-09-03.md`(피드 217건 해석표),
`kbond_issuer.py`(발행체 정본화 — 한국전력 발전 자회사 다섯이 한 글자씩만 달라 접두·편집거리로
접으면 한 통이 된다는 실측), `test_issuer.py`. `parse_kbond_logs.py` 와 `kbond_live.py` 의
`issuer_guess` 부근을 만진다.

**이 레인(React 이식)은 그 파일들을 안 건드린다.** 겹치는 곳은 없지만 같은 폴더이므로
시작 전에 `kbond_live.py`·`parse_kbond_logs.py` 의 mtime 과 `/health` 의 `ver` 를 적어 둘 것.

### I. 파일 지도

```
Projects\apps\kbond\
  kbond_live.py        엔진 + 옛 HTTP 서버 (start_engine 이 기동 경로)
  kbond_api.py         FastAPI 껍데기 (/api/view 가 계산된 값)
  kbond_view.py        ★화면이 하던 계산의 파이썬 판
  kbond_schema.py      응답 계약 (Pydantic) → openapi.json → kbond-api.d.ts
  kbond_live.html      옛 화면(토스 문법). 트레이더가 보는 것
  verify_v4.py         [A]~[H]
  test_frac.py         끝전 24건
  test_cors_token.py   문턱 31건
  parse_kbond_logs.py  파서 (다른 세션이 만지는 중)
  kbond_issuer.py      발행체 정본화 (다른 세션 것)

Projects\apps\kbond-web\      ★새 화면 (Next.js + CDS)
  src/app/{layout,page,providers}.tsx
  src/components/{Feed,Setup}.tsx
  src/lib/{api.ts, api-types.d.ts}    ← 주소가 정해지는 단 한 곳 · 타입은 기계 생성
  src/theme/                          ← v2 복사본 + kbond.css
  public/fonts/                       ← Pretendard SR

Projects\apps\ibond\          Vercel 에 올라가는 정적 화면(HTML 사본)
Projects\data\kbond\          원장·parquet·로그·prev_day 캐시
```
