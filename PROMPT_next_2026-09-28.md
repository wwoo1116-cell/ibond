# 다음 세션 인계 — K-Bond, 2026-09-28 · **경량화** (한 장)

> 09-11·09-15·09-22·09-23 네 판(1,219줄)을 이 한 장이 **대체한다.** 옛 판·RESULT·HANDOFF 39편은
> `archive/docs/` 에 그대로 있다 — «왜 그렇게 됐나» 가 궁금할 때만 연다. 이 장은 «무엇이·어디에·어떻게» 만 적는다.

## §0. 붙여 넣을 블록

```
K-Bond 레인. 2026-09-15 [OWNER] 「락만 고치고 얼린다」로 얼렸다. 09-22 화면 · 09-23 단가 · 09-28 경량화로
잠깐씩 열렸다. 개발을 이어서 하지 마라. 내가 지정하는 것만 한다.

정본 —  Projects\apps\kbond\PROMPT_next_2026-09-28.md   (이 한 장뿐 · 옛 판은 archive/docs/)

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

열려 있는 것 —
  [B] verify_v4 B2 국주 기준 민평(기존 · 동결 20260903 에선 안 남)   [C] 리더보드를 사람 이름 축으로?
  [E] won_to_bp 표가 테너 평균(짧은 쪽 24% 어긋남 · bp_per_won 이 답)   [F] 크레딧 단가 — 쿠폰 출처
  [G] 결제일 T+1 — 휴일표 없음   [H] 통안 민평 수집 결손 넷(지금은 계열 커브로 메움)
  [I] kbond_test.py test1/2/3 이 pytest 에 잡혀 늘 3 errors
  ~~[J] Vercel 배포~~ 닫힘 — 오너가 09-28 직접 배포(kbond-web.vercel.app 별칭 · 라이브에서 dyn 조각 200 확인).
      세션 안에서는 배포 명령이 차단되므로 앞으로도 오너 몫:  npx vercel deploy --prod --yes  (`!` 는 bash · 경로는 슬래시)
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

## §5. 함정 — 데인 것만

1. `Stop-ScheduledTask` 는 파이썬을 안 죽인다(conhost 래퍼) → `restart_kbond.ps1`. 2. 기동 되감기는 장 끝으로 갈수록 길다 — 안 뜬다고 다시 죽이지 마라.
3. 지문 대조는 동결로만·두 번. 4. Next `basePath` 는 CSS `url(/fonts/…)` 를 안 고친다 → `build_app.ps1` 의 `fix_font_prefix.py`(dyn 조각도 같은 치환).
5. 화면 HTML 은 `no-store`, 자산은 해시 — 열려 있던 탭은 Ctrl+Shift+R. 6. 셸을 지나는 패치에서 역슬래시·따옴표가 접힌다 → 파일 도구로, 앵커 1회 assert.
7. 재파싱 중 사전·코드 수정 금지. 8. `kbond_sector.json` 안 구우면 유동화가 회사채로 접힌다. 9. Miniconda 파이썬이 Funnel 인증서를 거절한다 → `curl`.
10. **`round(...,3)` 25곳을 4자리로 «열지 마라»** — 그 반올림이 복원값을 0.5bp 격자에 스냅한다(0.25bp 는 `lvl_q`·`set_mid` 가 따로 본다).
11. `gate_meaning` 은 원장 전체(846만 행·Message 열)를 올린다 — 9GB·25분. 다른 무거운 일과 겹치지 마라.
12. 글꼴 조각은 «어느 바이트를 받느냐» 만 바꾼다 — 조각 경계·축 범위를 손으로 고치지 말고 `gen_dyn_fonts.py` 를 다시 돌려라.
