# 백엔드 이식 1단계 — 계산을 서버로 (2026-09-03)

[OWNER] 「계산과 집계는 서버, 화면은 서버가 계산한 값을 쓴다」 · 「배포랑 상관없이 일단 로컬에서」

## 한 것

| 파일 | 무엇 |
|---|---|
| `kbond_view.py` (신설) | 화면이 하던 계산을 파이썬으로. uncross · best_of · med · bond_rows · cr_buckets · heat_cells · curve_points · cat_counts · mtx_group |
| `kbond_live.py` | `start_engine()` 추출 — 책 기동을 함수 하나로. 옛 판과 FastAPI 판이 **같은 것**을 부른다 |
| `kbond_api.py` (신설) | FastAPI 껍데기. `/health` `/book.json` `/feed.json` `/events` `/api/view` `/` |

**책 엔진·파서는 한 글자도 안 건드렸다.** 이 단계는 껍데기와 계산 위치만 옮긴다.

## 대조 — 화면과 같은 값을 내는가

동결 리플레이(2026-09-03 13:00)에서 화면 계산과 파이썬 계산의 **지문**을 맞댔다.
각 항목을 문자열로 만들어 정렬·연결한 뒤 SHA-1 앞 16자리. 소수는 `%.6f` 로 고정한다.

| 항목 | n | 파이썬 | 화면 | |
|---|---|---|---|---|
| 국고 행 | 32 | `5684bd5c319c7805` | 같음 | 일치 |
| 통안 행 | 6 | `e1a5d088317620b9` | 같음 | 일치 |
| 국민주택 행 | 4 | `eb9b97f0b6d0c2e6` | 같음 | 일치 |
| 크레딧 버킷 | 15 | `1107909c94047728` | 같음 | 일치 |
| 히트맵 칸 | 35 | `85eff12c9fa52a6d` | 같음 | 일치 |
| 탭 카운트 | 6 | 동일 | | 일치 |

★**처음엔 버킷·히트맵이 어긋났는데 값이 아니라 표기 차이였다** — JS `String(-3)` 은 `-3`,
파이썬 `str(-3.0)` 은 `-3.0`. 자릿수를 고정하니 같아졌다. 지문 대조를 할 때는
숫자 표기를 먼저 못 박을 것.

## 검증

- `verify_v4.py --port 8302` (FastAPI 판) **[A]~[H] 전건 통과** — 옛 판과 같은 책이다.
- `test_frac.py` 24건 · `test_cors_token.py` 31건 통과.
- feed 오류 0.

## 전송량

| | gzip |
|---|---|
| `/book.json` (옛 스냅샷) | 61 KB |
| `/api/view?lane=ktb` | 2.2 KB |
| `/api/view?lane=cr` | 2.7 KB |

화면이 `/api/view` 로 옮겨 가면 갱신마다 61KB 대신 2KB 가 간다.

## 겪은 함정

★**패치 스크립트가 자기가 넣은 코드를 다시 잘랐다.** `start_engine` 을 먼저 삽입하고
그 다음 `main()` 본문을 «`ref = {...}` 부터» 잘라내게 했더니, `s.index()` 가 새로 넣은
`start_engine` 안의 같은 줄을 먼저 찾아 `main()` 이 통째로 사라졌다(`NameError: main`).
**먼저 잘라내고 그 다음에 넣는다.** 백업(`.bak-engine`)에서 순서를 바꿔 복구했다.

## 다음

1. 화면을 `/api/view` 로 옮긴다 — `bondRows`·`crBuckets`·`heatCells` 호출을 fetch 로.
   그때 옛 계산 함수를 지우지 말고 «대조 모드» 로 한 판 돌려 지문이 같은지 본다.
2. 스키마 — 행 8종을 Pydantic 모델로. [OWNER 결정 대기]
3. React 이식. 타입이 생긴 뒤에.

## 실행

```
python -m uvicorn kbond_api:app --host 127.0.0.1 --port 8302        # 새 판
KBOND_REPLAY=20260903 KBOND_AT=13:00:00 KBOND_NO_MASK=1 ...          # 리플레이
python kbond_live.py                                                 # 옛 판(프로덕션 :8301)
```

## 2단계 — 스키마와 타입 (같은 날)

| 파일 | 무엇 |
|---|---|
| `kbond_schema.py` (신설) | 행 8종 + 계산된 뷰를 Pydantic 모델로. Quote · CreditQuote · Fill · FeedRow · Dealer · Event · Swap · Basket · BondRow · CreditBucket · Heat · Curve · View |
| `openapi.json` | FastAPI 가 낸 규격 (경로 6 · 모델 12 · 16KB) |
| `kbond-api.d.ts` | `openapi-typescript` 로 뽑은 TS 타입 (19KB). React 이식이 기계적 작업이 된다 |

**최상위 57키는 적지 않았다.** `hist`·`act`·`atbest` 처럼 키가 종목코드인 자유로운 dict 가
많아 모델로 적으면 장황해지기만 하고 잡히는 것이 없다. 화면이 `/api/view` 로 옮겨 가면
대부분 사라진다. 모든 필드에 `None` 을 허용한다 — 이 책의 규칙이 «값이 없으면 없다고
보이게 한다» 이고 타입이 그 규칙을 부정하면 안 된다.

### 재현성 확인

같은 동결 시점(09-03 13:00)에서 **옛 판(:8305)과 FastAPI 판(:8302)이 같은 지문**을 낸다
(`e79d9d5140e8ce1d`, 국고 32행). 서버가 낸 `/api/view` 와 그 스냅샷을 직접 계산한 값도 같다.

★중간에 지문이 달랐던 적이 있는데(`5684bd…` 14행) 원인은 **어제 책이 아직 안 실린 시점**의
스냅샷이었다. `load_prev` 는 백그라운드라 기동 직후 몇 초는 종목 목록이 짧다.
**대조는 어제 책이 실린 뒤에 할 것.**

### 디자인 [OWNER 2026-09-03 「디자인 문법은 v2와 동일하게」]

v2(`Projects\apps\sauron-v2`)의 문법을 확인해 두었다. React 이식 때 그대로 따른다.

- Coinbase CDS(`@coinbase/cds-web`) + `sauronTheme`(defaultTheme 얇은 파생)
- 폰트 **Pretendard SR** 자체호스팅. ★`local()` 없이 — 이 데스크에 Pretendard 가 없어
  옛 스택이 조용히 Malgun 으로 떨어졌던 실측 사고가 있다
- 굵기 **두 단계 400/600**(13px legal 만 500). 세 단계는 쓰지 않는다
- 행 높이 48 — 가상화가 이 값으로 스페이서를 계산하므로 실제로 48이어야 한다
- 방향 색은 CDS 슬롯이 아니라 `direction.css` 에 따로(CDS 의 green-good/red-bad 가 반대)
- `ThemeProvider` 하나, 중첩·라우트별 덮어쓰기 금지

**지금 배포된 HTML(토스 문법)은 건드리지 않는다** — 트레이더 피드백을 받는 중이다.
