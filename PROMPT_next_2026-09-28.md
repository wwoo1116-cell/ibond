# 다음 세션 인계 — K-Bond, 2026-09-28 · **경량화** (한 장)

> 09-11·09-15·09-22·09-23 네 판(1,219줄)을 이 한 장이 **대체한다.** 옛 판·RESULT·HANDOFF 39편은
> `archive/docs/` 에 그대로 있다 — «왜 그렇게 됐나» 가 궁금할 때만 연다. 이 장은 «무엇이·어디에·어떻게» 만 적는다.

## §0. 붙여 넣을 블록

```
K-Bond 레인. 2026-09-15 [OWNER] 「락만 고치고 얼린다」로 얼렸다. 09-22 화면 · 09-23 단가 · 09-28 경량화·문법·**트레이더**로
잠깐씩 열렸다. 개발을 이어서 하지 마라. 내가 지정하는 것만 한다.

정본 —  Projects\apps\kbond\PROMPT_next_2026-09-28.md          (이 파일 · 레인 상태·배관·함정)
        Projects\apps\kbond\PROMPT_next_2026-09-28-design.md   (화면 문법 — 09-28 오후 v2 이식)
        Projects\apps\kbond\PROMPT_next_2026-09-28-trader.md   (기능 — 09-28 저녁 «싼 것 고르기»)
        Projects\apps\kbond\PROMPT_next_2026-09-30-layout.md   (배치 «한 화면» — 09-29~30 · ★미커밋)
        옛 판은 archive/docs/

규율 —
- 백엔드를 만졌으면 셋 다: verify_v4 [A]~[I5] · gate_meaning [J][K][L](메모리 9GB · 25분) · pytest.
- 화면을 고쳤으면 동결 리플레이로 지문 대조 **두 번**(첫 실행은 거짓 양성) + 눈으로 한 장(§3).
- 재기동은 반드시  powershell -NoProfile -File restart_kbond.ps1  (태스크 Stop 은 파이썬을 안 죽인다).
- 정적 미리보기는 :3400 으로만(CORS 허용 목록에 그 포트뿐). 배포는 build_app.ps1 → vercel(§3).
- 불변식 «오퍼 금리 <= 비드 금리». 락(간격 0)은 걷지 않는다 — 09-15 판정.
- 본표 MPYieldDB·QuoteVsMP_bp 는 «그날 종가» 민평 — 장중·예측 문맥에선 선견이다.
- 지어낸 값은 빈칸보다 나쁘다 · 코드는 문자열 앵커로 끼우지 말고 앵커 1회 assert 뒤 넣어라 ·
  프레임 시간은 탭이 앞에 있을 때만 재라 · **고치기 전에 재라, 그 자리에서.**
- 귀속 규칙과 설명 변수가 축을 공유하면 그 상관은 검정이 아니다.
- **민평이 걸린 수는 날짜 축을 먼저 의심하라** — 문면 민평은 «전영업일» 것이고(하루 어긋남 하나가
  β 를 0.823 → −0.014 로 뒤집었다), 되감기는 REPLAY 와 무관하게 MAX(일자) 민평을 쓴다(20일 표류).
- **자가 초록이어도 안 지켜진다** — 새 칸·새 배지는 지문 비교 창(첫 15줄) 안에 들어오게 해 놓고 돌려라.

열려 있는 것 —
  [B] verify_v4 B2 국주 기준 민평(기존 · 동결 20260903 에선 안 남)   [C] 리더보드를 사람 이름 축으로?
  [E] won_to_bp 표가 테너 평균(짧은 쪽 24% 어긋남 · bp_per_won 이 답)   [F] 크레딧 단가 — 쿠폰 출처
  [G] 결제일 T+1 — 휴일표 없음   [H] 통안 민평 수집 결손 넷(지금은 계열 커브로 메움)
  [I] kbond_test.py test1/2/3 이 pytest 에 잡혀 늘 3 errors
  [M] 오퍼 표 정렬 — 잔존 순 유지? 「싼 것부터」 배지를 3위까지? (trader 정본 §8)
  ~~[J] Vercel 배포~~ 닫힘 — 오너가 09-28 직접 배포(kbond-web.vercel.app 별칭 · 라이브에서 dyn 조각 200 확인).
      세션 안에서는 배포 명령이 차단되므로 앞으로도 오너 몫:  npx vercel deploy --prod --yes  (`!` 는 bash · 경로는 슬래시)
  ★푸시도 오너 몫이고 **refspec 이라야 한다** — 두 리포가 같은 원격의 다른 브랜치로 간다.
      git push origin master:kbond-backend   (apps/kbond)      bare `git push` 는 조용히 아무것도 안 한다
      git push origin master:kbond-web       (apps/kbond-web)  (로컬이 둘 다 master 라 simple 이 거부)
```

## §1. 지금 서 있는 것 (배관 한 눈에)

| | |
|---|---|
| 백엔드 `:8301` | 태스크 `KBondLive` 08:20 · `conhost --headless … uvicorn kbond_api:app` · 기동 되감기 **~18초**(장 끝 기준 · 09-23 은 50초) |
| 화면 | `kbond-web` 정적 빌드 — `/app`·`/kbond/app`(out-kbond · Funnel) · `kbond-web.vercel.app`(out) · 옛 화면 `/`(kbond_live.html) |
| 일일 갱신 | `KBondDailyUpdate` 08:05·15:50 → `kbond_daily_update.py`(원장·다리·파생 표) · `KBondAppBuild` 08:00 |
| 아침 확인 | `Get-ScheduledTaskInfo KBondLive` · `curl :8301/health` · **`python kbond_fresh.py`(셋째가 판정 — 파생 표가 오늘 것인가)** |
| 자료 | `Projects\data\kbond\` 원장 parquet(846만 행) · 민평 DB(sim_portfolio) · 로그는 IMDH 두 방(블커본드·막무가내) |

`/health` 로 절약이 보인다 — `clients`(보는 사람) · `dirty` · **`raw_ver`**(전체 JSON 을 마지막으로 구운 판. `ver` 보다
작으면 아무도 안 달라고 한 것) · `px_settle`·`px_assume_quarterly`(단가 가정).

## §2. 09-28 경량화 — 잰 것과 자른 것 (전부 실측)

| 자리 | 전 | 후 | 어떻게 |
|---|---|---|---|
| 첫 화면 정적 무게(무압축) | **3,129,342B** | **1,573,711B** (−50%) | 글꼴 조각 + 아이콘 글꼴 제거 · gzip 경유 751,830B |
| 글꼴 | 2,057,894B 한 파일 | 456,200B (18조각) | Google 한국어 124 조각(unicode-range) → 96장 `public/fonts/dyn/` · `tools/gen_dyn_fonts.py` |
| 매초 굽는 삯(보는 사람 있을 때) | ~45ms | ~6ms | 전체 JSON 은 `raw_full()` 이 달라는 곳(옛 화면 SSE·/book.json)에서만 · 새 화면은 25KB lite 만 |
| 기동 되감기(09-23 하루 12,451건) | 49.9초 | 18.3초 | `coupon_dates` 메모(14.5초) · `_feed_one` 두 자리가 `_restore_memo` 를 거치게(19.4초) — 식은 그대로 |
| 리포 상단 | 135 항목 | 63 항목 | `.bak` 34·옛 화면 5·문서 39 → `archive/` (git mv · 지운 것 없음) |
| 인계문 | 4파일 1,219줄 | 이 한 장 | 옛 판은 archive/docs/ |

바꾸지 **않은** 것 — CDS(JS 783KB·CSS 195KB · 디자인 문법 「v2 와 동일」이라 오너 결정) · 옛 화면 `/`(아직 서빙) ·
`kbond_live.py` 의 옛 http.server(`replay_verify.py`·`test_cors_token.py` 가 쓴다) · 연구용 .py 14편(경로가 얽혀 그대로).

커밋 — kbond `6594901`(백엔드) `fbbe2e7`·`bc4c57a`(archive) · kbond-web `2b62db6`(글꼴) · 게이트 pytest **120**(+기존 3 errors) ·
verify_v4 **전건** · gate_meaning **전건**([J] 91.9% n=1,540) · 지문 대조 2회 0건 · 프로덕션 재기동 09:19(12초 만에 health).

## §3. 검증 레시피 (그대로 붙여 넣기)

```
cd C:\Users\infomax\Projects\apps\kbond
set KBOND_REPLAY=20260903&& set KBOND_AT=15:30:00&& python -X utf8 -m uvicorn kbond_api:app --host 127.0.0.1 --port 8303
python verify_v4.py --port 8303 --at 15:30:00 --day 20260903      # [A]~[I5]  (기동 60초 뒤)
python gate_meaning.py                                             # [J][K][L]  ★25분·9GB — 배경으로
python -m pytest -q                                                # 120 (+kbond_test 3 errors 는 [I])

cd ..\kbond-web && powershell -NoProfile -File build_app.ps1       # out(Vercel) + out-kbond(Funnel · 백엔드가 즉시 서빙)
python -m http.server 3400 --directory out
chrome --headless=new --remote-debugging-port=9222 --user-data-dir=%TEMP%\kbchrome about:blank
cd ..\kbond && node compare_screens.mjs http://127.0.0.1:8303/ http://127.0.0.1:3400/ http://127.0.0.1:8303   # ×2
node shot_screen.mjs http://127.0.0.1:3400/ http://127.0.0.1:8303 ob.png 국고 26-7
python tools\gen_dyn_fonts.py    (kbond-web · 글꼴 원본을 바꿨을 때만 · 30초)
```

## §4. 코드 지도 — 상단 .py 41편의 역할

- **런타임(11)** `kbond_api`(껍데기·끝점) → `kbond_live`(책 엔진 3,000줄 · 옛 http.server 포함) → `kbond_view`(화면 값 계산) ·
  `kbond_schema` · `kbond_price`(단가 정본) · `parse_kbond_logs` · `enrich_kbond_quotes`(복원 `restore`) · `kbond_issuer` ·
  `kbond_legs` · `kbond_catcall` · `mkt_curve_load`
- **일일(4)** `kbond_daily_update` · `kbond_fills` · `kbond_kis` · `kbond_fresh`
- **게이트·시험(12)** `verify_v4` · `gate_meaning` · `test_price`(정답지 32행) · `test_publish`(굽는 삯·raw_full) · `test_frac` ·
  `test_cors_token` · `test_issuer` · `test_fresh` · `test_stale_warn` · `kbond_test`([I]) · `replay_verify` · `verify_external`
- **연구·일회성(14)** `kbond_dyn_study` · `kbond_mark_test` · `slang_*`(4) · `kbond_issuer_{derive,near,todo,dict}` · `audit_kbond_parse` ·
  `backfill_amounteff` · `scrub_desk_names` · `kbond_sector`

## §4½. 화면 문법은 별도 정본이다 [2026-09-28 오후]

[OWNER] 「디자인 문법들 전반적으로 다듬기 — v2 문법 참조」로 화면 전체를 sauron-v2 문법에
맞췄다. **값은 한 자리도 안 바뀌었다**(지문 ×2 = 0건). 규칙·예외·함정은
`PROMPT_next_2026-09-28-design.md` 에 있다. 요지만:

- 차트 넷이 한 얼굴이 됐다 — 눈금 알고리즘 셋 → 하나(v2 `canonOptions`), 리드아웃은
  그림 밖 한 줄. 시세·맥박은 lightweight-charts, 커브는 SVG 유지(LWC 에 산점도가 없다).
- 서식 여섯 벌 → `lib/format.ts` 하나 · 변화는 화살표 ↗↘(v2 D4.1) · 방향색은 부호와 매매에만.
- 표 폭은 서식 최대치(`lib/columns.ts`) · 말줄임은 이름 칸에만(그것도 `title` 이 있을 때).
- **`guards/` 126개**가 이 규칙을 잰다(`pnpm test`) — 규칙을 외울 필요가 없다.
- 새 도구 둘: `probe_screen.mjs`(대비·넘침·글자폭) · `measure_load.mjs`(첫 화면 실제 바이트).
  화면을 고쳤으면 지문 ×2 · probe · 눈으로 한 장, 셋을 다 돌린다.

## §4¾. 트레이더가 쓸 것도 별도 정본이다 [2026-09-28 저녁]

[OWNER] 「트레이더 입장에서 쓸 수 있는게 잘 없어」로 크레딧 화면에 셋을 붙였다 —
**커브반영**(민평대비 − 그날 국고 커브 이동) · **또래 순위**(계열×등급×잔존 무리 안 몇 위) ·
**「싼 것부터」**(「민평에」를 감추고 싼 것부터 다시 세우는 보기). 정본은
`PROMPT_next_2026-09-28-trader.md`. 요지만:

- 요청은 「실시간 민평 추정」이었지만 그건 09-17 이 이미 막았다(16시에 얼고, 13시 오차
  분산의 82%가 「오후 커브를 모른다」). 대신 그 레인이 세워만 두고 **출하 안 한 벤치마크**를 냈다.
- 근거 β **0.823** · R² **0.643**(원장 138,032 종목일) · 남는 오차 1.00 → 0.57bp.
- **1년 안쪽에서는 커브반영이 거의 0 을 뺀다** — 국고 책의 최단 잔존이 1.3~1.8년이라서다.
  그 구간에서 「싼가」를 답하는 것은 **또래 순위** 쪽이다. 둘이 한 벌인 이유.
- ★설계를 **두 번** 바꿨고 두 번 다 측정이 바꿨다(책의 67%가 「민평에」 · 표는 60줄 상한).
- ★지문이 «운으로» 0건을 낸 전례가 생겼다 — 새 배지가 이름 칸에 숫자를 넣었는데 비교 창에
  마침 안 들어왔다. **새 칸·새 배지를 냈으면 창 안에 들어오게 해 놓고** 돌려라.

## §4⅞. 배치도 별도 정본이다 [2026-09-29~30] — ★코드가 **미커밋**이다

[OWNER] 「전체 페이지 스크롤을 ban 한다고 생각하고 짜보자」로 열렸다. 정본은
`PROMPT_next_2026-09-30-layout.md`. 요지만:

- **페이지는 이미 0 이었다** — 미끄러지던 것은 «판»(카드 격자)이다. 범인은 `58vh` 고정 캡
  (제 자리보다 짧게 자르면서 동시에 열을 넘치게 했다)과 판의 `align-items:start` + `overflow-y:auto`.
- 캐논 넷: 페이지·판은 안 구르고 **카드 몸통 `.kb-cb` 하나**가 구른다 · 남는 높이는 가중치로.
  원문은 `kbond-web/src/theme/kbond.css` 머리. 새 가드 `guards/layout-canon.test.ts` 가 잰다.
- 바닥은 **730px**(오너 결정). 실측: 여섯 탭 × 911·730 에서 페이지·판·열 전부 0.
- ★★★**가드가 «규칙» 아닌 «예외 목록» 을 재고 있어서 조용한 잘림 여섯 자리가 초록 아래
  살아 있었다.** 그리고 새로 쓴 가드도 같은 병으로 **두 번** 거짓 초록이었다 —
  ▎**새 시험은 수리를 되돌려 빨개지는지 확인하라.**
- ★`apps/kbond-web` 작업 트리에만 있다(HEAD `75b2c7f`). 시험 139 초록 · 린트 · 빌드 깨끗.
  커밋 · 푸시 · 배포는 오너 몫.

## §4⅞½. 시세 차트도 별도 정본이다 [2026-10-01] — ★**라이브다**

[OWNER] 「비드·애스크만 그리고 체결은 표시만. 현재가는 늘 우측, 과거는 옆으로. 어제자랑
연결해서 최대 1년.」으로 열렸다. 정본은 `PROMPT_next_2026-10-01-tape.md`. 요지만:

- **라이브러리는 답이 아니었다** — 토스·코인베이스·바이낸스 **넷 다 TradingView 집안**이고
  이 앱도 같은 집안이다(실측). 그들이 꽉 차 보이는 이유는 **밀도**이고(BTC 봉 하나에 수천 건
  대 26-1 하루 11건), 밀도는 옵션이 아니라 **어제까지를 이어서** 얻었다.
- 새 배관: `kbond_px_hist.py` 가 원장을 종목·날짜·분으로 접어 굽고(87만 행·2.1MB·5초),
  `GET /api/px_hist` 가 그것만 읽는다(책 안 읽음). 오늘은 `/api/view` 의 `px`+새 `px.fills`.
  화면이 `kbond-web/src/lib/pxTape.ts` 로 둘을 한 줄에 잇는다. **국고만** 이력이 있다.
- ★★**눈이 잡은 결함 셋이 전부 측정으로 확인됐다**: ① 그림이 **10.8:1** 이었고 범인은
  **메시지 카드**(가중치 2 를 물고 있었다) → 걷고 `w3` 로 **2.46:1** ② 매도·매수가 **보조선
  무게 1** 이었다 — 두 리포의 `addLine` 기본은 **2** 이고 1 은 밴드·이동평균 전용 ③ 여러 날
  축에 「12:40」이 날짜들 사이에 끼어 있었다(한 축이 두 단위).
- ★★**축 글자는 «만들 때» 넣어야 한다** — 라이브러리가 눈금 글자를 무게별로 캐시해
  `applyOptions` 로는 안 바뀐다(실측: 한 달 눈금이 전부 「08:30」). `uniformDistribution` 족속.
- 커밋 `1331c47`(백엔드) · `97c3ff3`+`9c9a167`(프런트) **전부 푸시됨** · :8301 **재기동함** ·
  Vercel **배포함**. ★★**깃 푸시로는 배포가 안 된다** — Vercel 은 로컬 `master` 를 CLI 로
  받는다(그래서 09-28 이후 4커밋이 라이브가 아니었다). `vercel --prod --yes`.

## §5. 함정 — 데인 것만

1. `Stop-ScheduledTask` 는 파이썬을 안 죽인다(conhost 래퍼) → `restart_kbond.ps1`. 2. 기동 되감기는 장 끝으로 갈수록 길다 — 안 뜬다고 다시 죽이지 마라.
3. 지문 대조는 동결로만·두 번. 4. Next `basePath` 는 CSS `url(/fonts/…)` 를 안 고친다 → `build_app.ps1` 의 `fix_font_prefix.py`(dyn 조각도 같은 치환).
5. 화면 HTML 은 `no-store`, 자산은 해시 — 열려 있던 탭은 Ctrl+Shift+R. 6. 셸을 지나는 패치에서 역슬래시·따옴표가 접힌다 → 파일 도구로, 앵커 1회 assert.
7. 재파싱 중 사전·코드 수정 금지. 8. `kbond_sector.json` 안 구우면 유동화가 회사채로 접힌다. 9. Miniconda 파이썬이 Funnel 인증서를 거절한다 → `curl`.
10. **`round(...,3)` 25곳을 4자리로 «열지 마라»** — 그 반올림이 복원값을 0.5bp 격자에 스냅한다(0.25bp 는 `lvl_q`·`set_mid` 가 따로 본다).
11. `gate_meaning` 은 원장 전체(846만 행·Message 열)를 올린다 — 9GB·25분. 다른 무거운 일과 겹치지 마라.
12. 글꼴 조각은 «어느 바이트를 받느냐» 만 바꾼다 — 조각 경계·축 범위를 손으로 고치지 말고 `gen_dyn_fonts.py` 를 다시 돌려라.
