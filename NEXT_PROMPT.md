# K-Bond 다음 세션 프롬프트 (2026-09-02 기준)

이 파일만 붙여 넣으면 이어서 할 수 있다. 자세한 것은 같은 폴더의
`KBOND_LANE_PROMPT.md`(§0~§11)에 있고, 절 번호로 짚어 두었다.

---

## 붙여 넣을 프롬프트

```
K-Bond 레인을 이어서 한다.
먼저 C:\Users\infomax\Projects\apps\kbond\KBOND_LANE_PROMPT.md 를 읽어라.
§1 «DECIDED» 는 다시 열지 않는다.
목적은 §11 — 장외 Order Book Dynamics 다. 파싱은 재료 만들기였다.

내가 지정하는 것만 한다. 임의로 분석을 시작하지 않는다.

[A] §11 — 목업(아티팩트 ba9dc24a)과 **라이브 레인 v1 가동 중**
    (127.0.0.1:8301 · 태스크 KBondLive 평일 08:20 · TTL 국고30분/크레딧2h
     = RESEARCH_microstructure.md). 남은 결정: 바구니 단위 · v2 우선순위
    (통안 사다리 / 크레딧 원 호가 / 체결 귀속 / 새 방 1반·니스·알프스).

[B] ~~은어 질문~~ — **목록 완결(§12).** 리서치로 넷(수N=수수료→FeeWon ·
    변고정 · 재정채=재정증권 · 신특), 오너 회신으로 둘(상단=민평 3사 상단값 ·
    화정=ㅎㅈ 오타→CONFIRM 편입). 남은 미해독어 없음 — 트레이더 질문지의
    C·D·E 절(민은/쩜/동/대치/예담/이자채)만 확인 대기.

[C] 남은 수리 — 다리 괄호짝 12,640 · kbond_fills 중복 제거.
```

---

## 지금 상태

| | |
|---|---|
| 본표 | `kbond_structured_data.parquet` **8,185,824행 · 54열** |
| 다리표 | `kbond_legs.parquet` **486,913행 · 42열** |
| 체결 | `kbond_fills.parquet` **84,011행 · 30열** |
| KIS 검증축 | `kbond_kis_curve.parquet` 25,143행 |
| 축약복원 | **98.1%** · `QuoteYield` 3,777,867 |
| 예약 태스크 | `KBondDailyUpdate` State=Ready. 트리거는 **평일 16:30 하나** |

**⚠ 행수가 8,331,933 에서 줄어든 건 결손이 아니다.** 이중 적재 146,948행을
걷어낸 결과다(§3 T20). 옛 숫자를 쓰는 문서가 있으면 이쪽이 맞다.

## 2026-09-02 오너 지시 다섯 — 집행 결과

| # | 지시 | 결과 |
|---|---|---|
| 1 | 장외 Order Book Dynamics 구현할 생각 | **§11 신설.** 설계 지시 대기 |
| 2 | 범주 콜 스키마 신설 | `TenorLo`·`TenorHi`·`SectorCat`·`RatingCat` — **159,190행 판정** |
| 3 | 국딱에 민평 붙이기 | `AuctionCode`·`AuctionTenor` — **6,231행** |
| 4 | 은어 표기로 보내기 | `kbond_은어_목록.xlsx` 발송 → **오너 회신 7개 반영**(수반=수수료 반값 등) + **내가 별칭 14개 자체 확인** · 남은 질문 6개 |
| 5 | 기계적 수리 | 넷 중 셋 완료(통안 표기·이중적재·신뢰등급). 다리 괄호짝만 남음 |

## 오너 결정 대기

**§11 설계 셋** — 호가 수명 · 바구니 단위 · 재게시 처리. 데이터가 못 정한다.
**은어 뜻** — 목록에 적어 주시면 반영한다.

## 이번에 데인 것 넷 (§3 T20~T23)

- **T20** 「1초 어긋난 이중 적재 2,427」이 실제로는 **152,950행**이었다(60배 과소).
  148,158쌍이 `.rtf`/`.txt` 두 형식에서 온 같은 메시지다.
- **T21** 신뢰등급을 「민평 5bp 이내」로 매기면 **`at_mp` 가 항등식이라 1등**이 된다.
  가장 검증 안 된 방식에 최고 등급이 갈 뻔했다.
- **T22** `extract()` 가 받지도 않은 `date` 를 참조했는데 `try/except` 가 삼켰다.
- **T23** 스플라이스가 옛 스키마를 물려받아 **새 열 4개를 통째로 버렸다.**
  51열이어야 할 산출물이 47열로 나온 걸 세어 보고서야 알았다.
  **열을 더했으면 산출물의 «열 수»를 세라.**

## 파일 위치

```
Projects\apps\kbond\   NEXT_PROMPT.md  KBOND_LANE_PROMPT.md
                       RESULT_ktb_slang.md  SLANG_INVENTORY.md
                       parse_kbond_logs.py  enrich_kbond_quotes.py
                       kbond_daily_update.py  kbond_legs.py  kbond_fills.py
                       kbond_kis.py  kbond_catcall.py  slang_inventory.py
                       slang_ktb_offset.py  slang_ktb_discriminant.py
                       audit_kbond_parse.py
                       artifacts\kbond_slang_questions.html
Projects\data\kbond\   *.parquet  kbond_은어_목록.xlsx
                       kbond_parse_state.json  kbond_daily_update.log
```
