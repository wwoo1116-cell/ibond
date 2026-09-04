# K-Bond 프롬프트 — Vercel 배포 배선 (v2 형태) (2026-09-03)

아래 코드블록을 그대로 다른 세션에 붙여 넣는다. 그 밑의 «근거» 절은 이 프롬프트가
인용하는 주소·설정·줄번호를 **이미 실측해 둔 것**이라, 받는 세션이 다시 재지 않고
인용하면 된다.

**코드는 아직 한 줄도 안 고쳤다. [0] 게이트부터 시작한다 — 그 결과에 따라 [1] 이후가 갈린다.**

**동시 세션 주의: 다른 세션이 `kbond_live.py` 의 `feed()` 계열(다리 분할)과
`kbond_live.html` 을 만지고 있다(`PROMPT_legs_live_2026-09-03.md`). 이 레인이 만지는 곳은
`kbond_live.py` 의 `Handler`(약 1694~1790)와 HTML 의 fetch/EventSource 네 줄뿐이다.
겹치지 않지만 같은 파일이다 — exact-match 치환만, 통째 재작성 금지, 시작 전 두 파일 mtime 을 적어 둘 것.**

---

## 붙여 넣을 프롬프트

```
K-Bond 라이브 화면을 Vercel 에 배포한다. sauron-v2(rateslab) 와 **같은 형태**다.
먼저 읽을 것:
- C:\Users\infomax\Projects\apps\kbond\KBOND_LANE_PROMPT.md — §1 DECIDED 는 다시 열지 않는다.
- C:\Users\infomax\Projects\apps\kbond\PROMPT_deploy_vercel_2026-09-03.md 의 «근거» 절 —
  Funnel 설정, v2 배선, 줄번호는 이미 재 놓았다. 다시 재지 말고 인용하라.
- C:\Users\infomax\Projects\apps\sauron-v2\README.md 의 «알아 둘 것» 절,
  C:\Users\infomax\Projects\apps\sauron-v2\backend\app\cors.py 의 머리글,
  C:\Users\infomax\Projects\apps\sauron-v2\src\lib\apiBase.ts 의 머리글.
  이 셋이 흉내 낼 규율이다. 특히 cors.py 가 «왜 * 가 아닌가» 를 이미 적어 뒀다.

동시 세션 주의: 다른 세션이 kbond_live.py 의 feed()/_feed_one/message_legs 와
kbond_live.html 을 만지고 있다. 이 레인은 kbond_live.py 의 Handler(약 1694~1790)와
HTML 의 fetch/EventSource 네 줄만 만진다. exact-match 함수 단위 치환만.
프로덕션 :8301 은 죽이지 않는다. 검증은 :8305 로 따로 띄운다.

## 오너가 정한 것 (DECIDED — 다시 열지 않는다)

[OWNER 2026-09-03] 「내 컴퓨터가 켜져있을 때 작동하게 할건데」
  → 책은 계속 이 PC 프로세스가 메모리에 든다. PC 가 꺼져 있으면 화면은 «백엔드 없음» 상태.
[OWNER 2026-09-03] 「배포는 Vercel로」 「사양을 v2랑 비슷한 방식으로」
  → 프런트 Vercel · 백엔드 이 PC · Tailscale 로 잇는다. v2 와 같은 삼각형.
[OWNER 2026-09-03] 노출 = **Funnel(공개) + 토큰**. (Serve 테일넷 전용 안을 보고 Funnel 을 고름)
[OWNER 2026-09-03] 프런트 리포 = https://github.com/wwoo1116-cell/ibond

## 오너 대기 (묻고 진행. 막히면 기본값으로 가되 보고에 적을 것)

- ibond 리포가 지금 **공개(public)**다. private 전환 권고는 전달됐고 오너 답을 안 받았다.
  기본값: 공개인 채로 진행하되 [4] 의 설계(주소·토큰을 리포에 안 넣음)로 공개여도 새지 않게 한다.
- React 이식과 백엔드 FastAPI 화는 이 프롬프트 범위가 **아니다**. 순서 권고는 «다음 레인» 절.

## 배포 형태

  브라우저 ──HTML── Vercel (ibond 리포, 정적)
      │
      └──JSON/SSE──> https://e110430.tailc7b701.ts.net/kbond ──Funnel──> 127.0.0.1:8301
                                                                         kbond_live.py
                                                                         (예약태스크 KBondLive 08:20)

  핵심: 데이터 요청은 **Vercel 서버가 아니라 보는 사람 브라우저**가 한다.
  Vercel 은 HTML 한 장만 배달한다. 원장·책·민평은 이 PC 밖으로 안 나간다.

## [0] 게이트 — 코드 한 줄 쓰기 전에 이것부터 잰다

SSE 가 Funnel 을 통과하는가. 버퍼링하는 프록시는 /events 를 죽이고, 화면 전체가
거기 걸려 있다. 통과 못 하면 [1] 이후의 설계가 통째로 바뀐다(폴링 대체).

  1. tailscale funnel --bg --set-path /kbond http://127.0.0.1:8301
     (기존 / → :8100 과 /v2 → :8200 은 건드리지 않는다. «근거» B 에 현재 설정 전문)
  2. curl -N --max-time 20 https://e110430.tailc7b701.ts.net/kbond/events
  3. 판정: 20초 안에 data: 프레임이 **둘 이상** 흘러나오면 통과.
     하나 오고 멈추거나, 20초 뒤에 한꺼번에 쏟아지면 버퍼링 — 실패.
  4. /feed.json 도 한 번: curl -s ".../kbond/feed.json?limit=5" | head -c 300
  5. 결과를 먼저 보고한다. 실패면 여기서 멈추고 오너에게 폴링 대체안을 묻는다.

주의: 이 시점의 :8301 은 토큰이 없다. 게이트 확인이 끝나면 [1] 을 끝낼 때까지
tailscale funnel --https=443 --set-path /kbond off 로 닫아 둔다.

## [1] 백엔드 — CORS + 토큰 (kbond_live.py)

지금 Handler 는 CORS 헤더를 **하나도** 안 보낸다(«근거» C). 오리진이 갈리는 순간
네 엔드포인트가 전부 브라우저에서 막힌다.

  (a) 토큰. 환경변수 KBOND_TOKEN.
      - 설정돼 있으면 /events · /book.json · /feed.json 은 ?t=<토큰> 을 요구한다.
        틀리거나 없으면 401, 본문 없음.
      - 비교는 hmac.compare_digest. 토큰 값을 로그에 절대 남기지 않는다.
      - /health 는 토큰 없이 {"ok":true} 만 준다. 토큰이 맞으면 지금의 상세를 준다.
      - KBOND_TOKEN 이 없으면 토큰 검사를 하지 않는다(로컬 전용 개발 그대로).
        단 그때는 기동 로그에 «토큰 없음 — Funnel 에 걸지 말 것» 을 한 줄 남긴다.
      - 왜 헤더가 아니라 쿼리인가: EventSource 는 커스텀 헤더를 못 싣는다.
        네 요청 모두 헤더 없는 단순 GET 이 되어 프리플라이트도 필요 없어진다.
        대가: 토큰이 프록시 접근로그에 남을 수 있다. 이 규모에서는 받아들인다.
  (b) CORS. cors.py 규율 그대로 — * 금지, 오리진 에코 + Vary: Origin.
      허용 정규식 기본값: \Ahttps://ibond(-[a-z0-9-]+)?\.vercel\.app\Z
      (Vercel 프로젝트 이름이 ibond 가 아니면 실제 도메인을 보고 고친다)
      환경변수 KBOND_ALLOWED_ORIGINS(콤마), KBOND_ALLOWED_ORIGIN_REGEX 로 덮어쓸 수 있게.
      앞뒤 앵커를 반드시 넣는다. cors.py 가 적어 둔 세 가지는 거절되어야 한다:
        https://ibond.vercel.app.evil.com / https://evil-ibond.vercel.app / http://ibond.vercel.app
  (c) /events 응답에도 같은 CORS 헤더가 붙어야 한다(EventSource 도 CORS 를 탄다).
      SSE 는 스트림이라 헤더를 나중에 못 붙인다. send_header 순서를 확인할 것.
  (d) 401·CORS 거절은 건수만 로그에 센다. 오리진 문자열은 80자로 잘라 남긴다.

  검증: 새 시험 파일 test_cors_token.py.
    - 토큰 없음 → 401, 틀린 토큰 → 401, 맞는 토큰 → 200
    - 허용 오리진 → ACAO 에코, 거절 오리진 셋 → ACAO 없음
    - KBOND_TOKEN 미설정이면 토큰 검사 안 함
    - /health 는 토큰 없이 200
  검증용 서버는 :8305 로 띄운다. 프로덕션 :8301 을 건드리지 않는다.

## [2] 프런트 — API 베이스 한 곳 + 토큰 입력 (kbond_live.html)

지금 HTML 은 상대주소로 네 번 부른다(«근거» D). 이걸 한 곳으로 모은다.
apiBase.ts 의 규율을 그대로 옮긴다 — **읽는 곳은 하나다**.

  (a) 최상단에 상수 하나:
        const API = localStorage.getItem("kbond.base") || "";   // "" = 같은 출처
        const TOK = localStorage.getItem("kbond.tok")  || "";
      네 호출을 헬퍼 하나로 바꾼다. 헬퍼가 API 와 ?t= 를 붙인다.
      로컬(http://127.0.0.1:8301/)에서는 둘 다 비어 있어 지금과 완전히 같이 동작한다.
  (b) 첫 진입 설정 화면. API 가 비었고 같은 출처에 /health 가 없으면
      «서버 주소»·«토큰» 두 칸을 받아 localStorage 에 넣고 새로고침한다.
      ★ 이 설계의 요점: 주소도 토큰도 **리포에 안 들어간다**. 공개 리포여도 샐 것이 없다.
      Vercel 에 굽는 값이 없으므로 v2 의 NEXT_PUBLIC_API_BASE 자리는 비어 있다.
  (c) 401 을 받으면 저장값을 지우고 설정 화면으로 돌아간다.
  (d) 헤더 어딘가에 «설정» 버튼 하나(주소·토큰 다시 넣기).
  (e) 지금의 esc() 규율(74곳)과 스크롤 보존(1192·1508)은 손대지 않는다.

  검증: 로컬 :8305 에 대해 (1) 같은 출처로 열었을 때 지금과 동일,
        (2) 다른 포트에서 열어 주소·토큰을 넣으면 붙는지.

## [3] Funnel 다시 켜기

[1] 이 끝나 토큰이 서면 /kbond 를 다시 연다. 그리고 [0] 의 curl 을 토큰 붙여 재실행.
토큰 없이 부른 curl 이 401 인지도 같이 확인한다 — 이게 문턱이 실제로 섰다는 증거다.

## [4] ibond 리포 + Vercel

리포에는 **뷰어만** 올린다. 확인해 뒀다(«근거» E): 화면 코드에는 하우스·딜러·은어 표가
하나도 없다. 전부 백엔드에 있다(kbond_live.py:576 house_of, parse_kbond_logs.py, issuer_ratings.json).

  ibond/
    public/index.html   ← kbond_live.html 복사본
    vercel.json         ← framework 없음(정적)
    README.md           ← 이게 무엇이고 백엔드는 어디 있는지 세 줄
    .gitignore

  올리지 않는 것: kbond_live.py · parse_kbond_logs.py · enrich_kbond_quotes.py ·
  kbond_legs.py · kbond_fills.py · issuer_ratings.json · kbond_은어_목록.xlsx ·
  prev_day_*.json · *.parquet · 로그 전부. .gitignore 에 명시한다.

  ★ 복사본이 생기는 것에 주의. index.html 은 kbond_live.html 의 사본이라 둘이 갈라진다.
  당장은 «HTML 을 고치면 복사한다» 를 README 에 적고, 자동화는 다음 레인에서 한다.

  검증: 배포 뒤 실제 도메인을 확인하고 [1](b) 의 정규식이 그 도메인을 무는지 다시 잰다.
  프리뷰 도메인도 한 번 열어 본다.

## [5] 끝단 검증

  - 이 PC 브라우저에서 https://ibond*.vercel.app 을 열고 주소·토큰을 넣어 책이 서는지
  - SSE 로 새 호가가 실시간으로 들어오는지(장중에)
  - 폰(테일넷 아닌 회선)에서도 되는지 — Funnel 을 고른 이유가 이것이다
  - 토큰 없이 https://e110430.tailc7b701.ts.net/kbond/book.json 이 401 인지
  - verify_v4.py 를 :8305 기준으로 한 번 돌려 [A]~[G] 가 그대로인지(회귀 없음 확인)
  - KBondLive 예약태스크에 KBOND_TOKEN 이 전달되는지. 사용자 환경변수로 넣으면
    태스크가 물려받는다(v2 의 BW_MYSQL_* 와 같은 방식, README «알아 둘 것»).

## 하지 말 것

- HOST 를 0.0.0.0 으로 바꾸지 말 것. Tailscale 이 127.0.0.1 로 프록시한다. 문은 하나로 둔다.
- CORS 를 * 로 열지 말 것. 이 API 의 문턱은 토큰과 CORS 둘뿐이다.
- Book 엔진·파서·스냅샷 스키마를 건드리지 말 것. 이 레인은 껍데기만 만진다.
- kbond_live.html 을 통째로 재작성하지 말 것(동시 세션이 같은 파일을 만진다).
- 프로덕션 :8301 을 죽이지 말 것.

## 보고

각 항목마다 무엇을 어떻게 쟀는지와 명령 출력을 붙인다. 끝나면 커밋 해시와
git show --stat. [0] 게이트 결과는 다른 것을 시작하기 전에 먼저 보고한다.
```

---

## 근거 (이미 실측함 — 다시 재지 말 것)

### A. sauron-v2 배선 (흉내 낼 원본)

```
프런트   Vercel               https://rateslab.vercel.app
백엔드   이 PC :8200 FastAPI  예약태스크 SauronV2Backend 가 로그인 때 기동
노출     Tailscale Funnel     https://e110430.tailc7b701.ts.net/v2 → 127.0.0.1:8200 (접두사 벗김)
배선     NEXT_PUBLIC_API_BASE 를 빌드 시각에 번들로 굽는다. 읽는 파일은 src/lib/apiBase.ts 하나.
문턱     backend/app/cors.py  DEFAULT_ORIGIN_REGEX = \Ahttps://rateslab(-[a-z0-9-]+)?\.vercel\.app\Z
가드     guards/production-env.test.ts 가 빌드 산출 청크를 읽어 주소가 실제로 박혔는지 확인
```

cors.py 머리글이 스스로 밝혀 둔 것: **그 API 는 인증이 없고 Funnel 로 공개돼 있어서
CORS 가 유일한 문턱이다.** K-Bond 는 새어 나가는 것이 딜러 실명과 호가 원문이라
같은 급이 아니다 — 그래서 토큰을 더한다. (오너가 Funnel 을 고르며 토큰을 같이 골랐다)

### B. Tailscale 현재 설정 (`tailscale funnel status`, 2026-09-03 실측)

```
# Funnel on:
#     - https://e110430.tailc7b701.ts.net
#     - https://e110430.tailc7b701.ts.net:8443

https://e110430.tailc7b701.ts.net (Funnel on)
|-- /   proxy http://127.0.0.1:8100
|-- /v2 proxy http://127.0.0.1:8200

https://e110430.tailc7b701.ts.net:8443 (Funnel on)
|-- / proxy http://127.0.0.1:8200
```

`/kbond` 는 비어 있다. `/` 는 v1(braveworld :8100), `/v2` 는 rateslab :8200 이 쓴다.
Funnel 은 **포트 단위**로 켜진다(443 과 8443 각각 «Funnel on»). 443 에 경로를 더하면
그 경로도 공개다 — 이번에는 그것이 의도다.

### C. kbond_live.py 현재 상태

```
2013줄. HOST/PORT = 127.0.0.1:8301 (:60) · POLL_S = 0.4 (:71)
엔드포인트: /events(:1694, SSE) · /health(:1721) · /book.json(:1733) · /feed.json(:1742)
CORS 헤더: 없음 (grep -n 'Access-Control' → 0건)
토큰·인증: 없음
house_of(:576) — 딜러→하우스 매핑은 백엔드에만 있다
하드코딩 절대경로 7곳: kbond_live.py:103,1799 · parse_kbond_logs.py:57,58 ·
  enrich_kbond_quotes.py:69 · kbond_legs.py:57 · kbond_fills.py:54
원천: SRC_DIR = C:\Users\infomax\Documents\K-Bond Messenger Chat (parse_kbond_logs.py:57)
```

### D. kbond_live.html 현재 상태

```
2011줄. 상태→화면 구조는 이미 서 있다: SNAP → render()(:1863) → 서브 렌더러 21개
같은 출처 호출 네 곳:
  :1480  fetch("/feed.json?limit=3000")
  :1839  fetch(`/feed.json?limit=24000&${q}`)
  :1999  new EventSource("/events")
  :2006  fetch("/book.json")
이스케이프: const esc(:534), 사용 74곳. 딜러가 친 원문도 esc(e.raw)(:1097)
스크롤 보존: 테이프(:1192,1195) · 피드(:1508,1511) «바닥에 붙어 있었으면 바닥 유지»
```

이 셋(구조·이스케이프·스크롤)이 이미 처리돼 있다는 것이, 이번 레인에서
**HTML 을 재작성하지 않고 네 줄만 고치면 되는** 이유다.

### E. 리포에 올려도 되는 것

`kbond_live.html` 에는 하우스·딜러·은어 표가 없다. 전부 JSON 으로 받아 그리기만 한다.
(HTML 에서 house_of·HOUSE 0건, 방 이름 문자열 3건뿐)
따라서 뷰어 한 장은 공개 리포에 올려도 내부 사전이 새지 않는다.
다만 [2](b) 설계로 **주소와 토큰까지 리포 밖**에 두면 공개 여부와 무관해진다.

### F. ibond 리포 상태 (GitHub API, 2026-09-03 실측)

```
wwoo1116-cell/ibond   private: false   default_branch: main
created 2026-09-03T05:25:49Z   size 0   "This repository is empty."
```

비어 있다. 아직 샌 것은 없다. private 전환 권고는 오너에게 전달됐고 답은 못 받았다.

### G. 토큰이 번들에 못 들어가는 이유 (이미 판정)

v2 의 `NEXT_PUBLIC_*` 처럼 빌드 시각에 굽는 값은 브라우저에서 그냥 보인다.
페이지가 공개인 이상 거기 실린 토큰은 비밀이 아니다. 리포를 private 으로 바꿔도 같다.
→ 그래서 토큰은 사람이 넣고 localStorage 에 산다([2](b)). 리포에도 번들에도 없다.

---

## 다음 레인 (이 프롬프트 범위 밖)

오너 질문: 「HTML이 아니라 React랑 백엔드를 제대로 찍어야 하지 않을까」 — 답은 «맞다,
다만 순서가 반대다». 근거와 권고 순서:

1. **백엔드 먼저.** `snapshot()` 이 뱉는 dict 가 이 시스템의 유일한 계약인데 어디에도
   안 적혀 있고, 화면이 그걸 21곳에서 손으로 읽는다. 그 계약이 깨진 전례가 이미 있다
   (크레딧 KeyError 회귀를 타입도 시험도 아닌 런타임 검증기 [F4b] 가 잡았다).
   HTTP 껍데기만 FastAPI 로 옮기면 CORS·토큰이 미들웨어 두 줄이 되고 스키마가 따라온다.
   **Book 엔진은 건드리지 않는다.**
2. 스키마 → TS 타입 생성.
3. 그때 React 이식. 21개 render 함수 → 컴포넌트. 타입이 있으면 기계적 작업이 된다.

React 를 먼저 하면 «적히지 않은 계약을 두 번 손으로 베끼는» 셈이 된다.
착수 시점은 **다리 분할 레인이 끝난 뒤**다. 지금 시작하면 백엔드 한복판에서 충돌한다.

HTML 을 «썩었으니 갈아엎는다»는 근거로 흔히 드는 것들은 이 파일에 해당하지 않는다:
구조는 이미 상태→렌더고(«근거» D), 이스케이프는 74곳에서 지켜지고 있고, 전면 재구축이
스크롤을 날리는 문제도 처리돼 있다. 이식으로 얻는 것은 정확성도 성능도 아니라
**v2 와 같은 규율(타입·가드·시험·디자인 토큰)** 이다. 그 값은 화면이 자랄수록 커지고,
미완 목록(원 호가 잔여·미해석 265건·지방물 종목 확정·크레딧 TTL 레벨지속)을 보면 자란다.
2011줄은 옮길 만하고 4000줄은 못 옮긴다 — 그래서 «다음»이지 «나중에 언젠가»가 아니다.
