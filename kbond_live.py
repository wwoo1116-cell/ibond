# -*- coding: utf-8 -*-
"""장외 호가창 라이브 레인. [OWNER 2026-09-02 「지으세요」]

## 무엇인가

메신저 자동저장 로그의 **오늘 파일 꼬리**를 5초마다 증분으로 읽어 파싱하고,
목업과 같은 규약((딜러,방향[,종목]) 절대값 교체)으로 오늘 책을 접어
localhost 로 서빙한다. 실측(2026-09-02 14:24): 메신저는 버퍼 없이 즉시 flush
하므로 끝단 지연 = 폴링 주기 + 1초 미만.

## 본표 배치와의 관계 — 완전 분리

이 레인은 `kbond_structured_data.parquet` 을 읽지도 쓰지도 않는다.
T24(낮에 본표를 읽다 교체와 충돌)를 만들 이유가 없다. 재료는 원본 로그 꼬리와
아침에 한 번 로드하는 민평뿐이고, 산출물은 메모리 안의 책과 /book.json 뿐이다.

## TTL 기본값 = 리서치 결과 [2026-09-02]

내부 실측(같은 (딜러,종목,방향) 재게시 간격):
    국고   중앙 1.2분 · p90 17.2분 · p95 44.4분  -> 30분이 재게시의 93.3% 포괄
    크레딧 중앙 6.1분 · p90 47.3분 · p95 123.7분 -> 120분이 94.7% 포괄
외부: Bloomberg CBBT 가 «가장 최근 executable 호가» 원칙(최신성 우선), BGN 은
indicative 포함 — 우리 호가는 indicative(runs 문헌: Hendershott et al. 2025)라
하드컷 + 화면의 나이 바램(soft decay) 병행이 맞다.
    -> 기본값: 국고·통안 TTL 30분, 크레딧 TTL 120분. 뷰어에서 토글 가능.

## v1 범위 (의도적 축소)

- 국고: BondCode + 축약호가(restore, 민평 기준) + 문면 절대금리
- 크레딧: 문면 bp 스프레드(sign/overunder)만 — «원» 호가는 TTM 환산이 필요해 v2
- 통안: 은어 사다리(MSB)가 DB 마스터를 더 물어야 해서 v2
- 체결 테이프: CONFIRM 원문 그대로 (fills 파이프라인 미태움)

실행:  python kbond_live.py            (기본 127.0.0.1:8301)
       예약 태스크 KBondLive 가 평일 08:20 에 pythonw 로 띄운다.
"""
from __future__ import annotations

import gzip
import hmac
import json
import os
import re
import sys
import threading
import time
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from parse_kbond_logs import ROOMS, SRC_DIR, extract, split_messages   # noqa: E402
from enrich_kbond_quotes import (MSB_ORDER, MSB_SLANG, RE_MP_FRAC, engine,   # noqa: E402
                                 maturity_to_ts, norm_code, restore, won_to_bp)
from parse_kbond_logs import RE_LIST_FRAC, split_broker                # noqa: E402
import kbond_issuer                                                   # noqa: E402
import kbond_catcall                                                    # noqa: E402
from kbond_legs import split_legs                                       # noqa: E402

HOST, PORT = "127.0.0.1", 8301
# ★리플레이(개발·검증 전용): `python kbond_live.py --replay 20260902 --port 8302`
# 그날 로그 전체를 한 번에 접고 «가상 시계»를 마지막 메시지 시각에 세운다.
# 프로덕션 경로는 REPLAY=None 일 때와 한 글자도 다르지 않다.
REPLAY = None
# ★--at 은 «동결» 이다. 이걸 안 걸면 오늘 날짜를 리플레이할 때 폴링이 계속
#   새 메시지를 먹어 시계가 흘러가고, 그 시점 책이 아니라 지금 책이 된다.
REPLAY_AT = None
# ★v1.1 [OWNER 「거의 동시에」]: 원천 flush 가 0초 실측이므로 병목은 우리 폴링뿐.
# 파일 stat 몇 개는 공짜라 0.4초로 내리고, 뷰어에는 SSE 로 «밀어» 준다.
# 끝단 지연 = 파일 폴링(<=0.4s) + 푸시(~0) ≈ 0.5초 미만.
POLL_S = 0.4
VIEWER = Path(__file__).parent / "kbond_live.html"
TTL_DEFAULT = {"ktb": 1800, "credit": 7200}      # 리서치 결과 (독스트링)
# 크레딧 책에 합류하는 계열 [OWNER 2026-09-07 「저것도 책 경로 열어주고」].
# 문면 꼴이 크레딧과 «똑같다» — 만기 + 민평 + 끝전 + 등급 + 팔자. 새 탭을 만드는 대신
# 같은 경로로 접으면 히트맵·버킷·커브·수요매칭이 전부 따라온다.
MSB_MP_WIN = 30          # 통안 민평 폴백 창(일). 7일은 실측에서 모자랐다
# ★[2026-09-07] «민+3팔자» 처럼 단위 없는 민평 대비 스프레드. RE_SPREAD 는 bp/원 을
#   요구해 못 읽는다(크레딧 매도 4,356행 = 0.16%). 단위는 데이터로 안 가려진다 —
#   무단위 값 분포(중앙 2.0·75% 3.0)가 bp(중앙 2.00·75% 4.00)와 원(1.00·2.00) 사이다.
#   ⚠그래서 «민평 그 자리» 로도 읽지 않는다. 틀린 레벨을 박느니 레벨을 비운다.
#   verify [K] 가 이 수를 세고, 튀면 새 문형이 생긴 것이다.
RE_MP_SIGNED_NOUNIT = re.compile(
    r"민\s*평?\s*[+\-]\s*\d{1,3}(?:\.\d{1,2})?(?!\s*(?:bp|비피|빕|삡|원|\d))")
CR_LANE = ("크레딧/기타", "MBS", "지방/첨가소화", "국고이자채")
# 종별은 계열에서 강제한다 — 발행체명 규칙에 안 걸린다("주금공MBS" 는 규칙상 회사채).
# ★[OWNER 2026-09-10] 계열을 «위험순» 으로 바꿨다. 레인이 곧 계열인 것들도 따라간다 —
#   [OWNER] 「MBS 만 따로」이므로 국민주택·국고이자채·물가채는 무위험으로 간다.
CR_CLS = {"MBS": "MBS", "지방/첨가소화": "무위험", "국고이자채": "무위험",
          "국민주택": "무위험", "물가채": "무위험", "국고": "무위험",
          "통안": "무위험", "국고/통안": "무위험"}
# ★v8 TTL 재검토 (2026-09-03 실측, 21영업일 국고 재게시 44,515쌍 — RESULT_ttl_review.md)
#   같은 (딜러,종목,방향) 재게시에서 «레벨이 1bp 이상 움직였을» 확률, 나이 구간별.
#   0-5분 0.7% · 5-15분 5.1% · 15-30분 14.1% · 30-60분 25.9% · 1-2시간 41.8% · 2h+ 54.2%
#   (레벨이 «조금이라도» 바뀐 비율은 12 · 41 · 61 · 70 · 79 · 85%.)
#   -> 하드컷 30분은 유지하고, 화면은 5분·15분에서 두 단계로 바랜다(soft decay).
#   ⚠ 조건부 확률이다(재게시가 관측된 쌍만). 딜러가 바뀔 때 더 자주 다시 부른다면
#     «안 바뀜» 은 과소 — 실제 지속은 이보다 좋다. 명시적 철회(취소·정정)는
#     21일에 10행뿐이라 삭제 이벤트로 못 쓴다: 삭제 = TTL 뿐.
TTL_EVIDENCE = {"ktb": [[300, 0.7], [900, 5.1], [1800, 14.1], [3600, 25.9],
                        [7200, 41.8], [86400, 54.2]]}
AGE_STEPS = (300, 900)      # 화면 바램 단계(초): 신선 <5분 · 익음 5~15분 · 노후 15분+
# ★v8 체결 귀속 창 (m_fill.py 검증, 라벨 2,711건을 미상으로 가정해 예측)
FILL_LEVEL_WIN = 1800       # 레벨 일치 + 같은 브로커, 30분 안 -> 99.4%
FILL_PREV_WIN = 60          # 맨 ㅎㅈ -> 같은 브로커 직전 호가, 60초 안 -> 92.9%
# ★[OWNER 2026-09-03] weak(60~300초, 적중 71.6%)는 «빼기». 네 건 중 한 건이 틀리므로
#   맞는 체결 30% 를 잃더라도 지어낸 귀속을 남기지 않는다. 60초를 넘으면 내용 없음으로 센다.
CROSS_MIN_BP = 0.5          # 크로스 이벤트 문턱 [OWNER] — 같은 레벨(락)은 이벤트가 아니다
PULSE_BIN = 600             # 시장 맥박·종목 활동 버킷 (10분)
BIG_AMT = 300               # 이벤트 «대량»: 표기 수량 300억 이상
LANE_OF = {"국고": "ktb", "통안": "msb", "국민주택": "nhb", "크레딧/기타": "cr",
           "지방/첨가소화": "muni"}
PREV_V = 2                  # 어제 캐시 버전 (pulse 가 없으면 다시 접는다)

# 국민주택 1종 은어 사다리. 긴 낱말이 먼저 걸려야 한다(국전전·국전당이 국전보다 앞).
# 뜻은 SECTOR_RULES(parse_kbond_logs) 의 판별검정 주석에 있다: 당월/전월/전전월.
DUP_WIN = 20        # 방을 가로지르는 중복으로 볼 시간 창(초)
NHB_ORDER = ("국전전", "국전당", "국당", "국전")
NHB_LABEL = {"국당": "당월", "국전": "전월", "국전전": "전전월", "국전당": "전월·당월"}

LOG = Path(r"C:\Users\infomax\Projects\data\kbond") / "kbond_live_server.log"


def today_str():
    """오늘(리플레이면 그날). SQL 파라미터·파일 글롭이 같은 날을 봐야 한다."""
    return (f"{REPLAY[:4]}-{REPLAY[4:6]}-{REPLAY[6:]}" if REPLAY
            else date.today().strftime("%Y-%m-%d"))


def log(msg):
    """pythonw 는 콘솔이 없어 print 가 증발한다(T25). 파일에 남긴다."""
    line = f"{datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + chr(10))
    except OSError:
        pass


STATE = {"lock": threading.Lock(), "book": {}, "raw": b"{}", "ver": 0,
         "t0": time.time(), "last_evt": 0.0, "stream": []}
COND = threading.Condition()

# 등급 서열 (매칭용). 앞일수록 좋다.
RATING_ORDER = ["AAA", "AA+", "AA0", "AA-", "A+", "A0", "A-", "BBB+", "BBB0", "BBB-", "BBB"]
def rating_rank(r):
    r = (r or "").split("(")[0]
    return RATING_ORDER.index(r) if r in RATING_ORDER else None


# ───────────────────────────────────────────── 민평 (아침 1회)
def load_mp_latest():
    """최신 일자의 국고 지표코드 -> 민평. 전일 민평 대비가 딜러 호가 관행이다.

    ★2026-09-02 검증에서 잡힌 구멍: ontherun_schedule 은 지표지정일까지만 있어
    (실측 2026-06-10 이 마지막) 그 뒤 발행된 26-7·26-9 같은 새 종목의 ISIN 이
    없었고, 그 종목 호가가 책에서 통째로 빠졌다. `국채_발행정보` 의 종목명이
    'YY-N' 꼴이라 여기서도 매핑을 얻어 **합집합**으로 쓴다.
    """
    from sqlalchemy import text
    with engine().connect() as c:
        otr = pd.read_sql(text(
            "SELECT DISTINCT 종목명, 표준코드 FROM ontherun_schedule"), c)
        iss = pd.read_sql(text(
            "SELECT 표준코드, 종목명 FROM `국채_발행정보` "
            "WHERE 종목명 REGEXP '^[0-9]{1,2}-[0-9]{1,2}$'"), c)
        mats = pd.read_sql(text(
            "SELECT 표준코드, 만기일, 인포맥스소분류, 표면이율 FROM `국채_발행정보`"), c)
        onames = pd.read_sql(text(
            "SELECT DISTINCT 종목명 FROM ontherun_schedule WHERE 종목명 LIKE '국고%'"), c)
        bench = pd.read_sql(text(
            "SELECT 일자, 만기, 종목명 FROM ontherun_schedule "
            "WHERE 변경내용='지표지정' AND 종목명 LIKE '국고%'"), c)
        d0 = pd.read_sql(text("SELECT MAX(일자) d FROM `국고통_민평`"), c)["d"][0]
        mp = pd.read_sql(text(
            "SELECT 종목코드, 민평 FROM `국고통_민평` WHERE 일자 = :d"),
            c, params={"d": str(d0)})
        # ★v4 [OWNER 2026-09-03] 「국당·국딱은 국민주택과 국채를 혼용한다 —
        #   그날이 국채 입찰일인지에 따라 다를 듯」. 그래서 그날 입찰을 읽어
        #   화면에 «오늘은 국채 입찰일» 이라고 띄운다(자동 재배정은 하지 않는다.
        #   판별검정 결과는 RESULT_slang_nhb_auction.md).
        auc = pd.read_sql(text(
            "SELECT 표준코드, 종목명, 만기, 낙찰금리 FROM `국채_입찰` "
            "WHERE 구분='경쟁' AND 입찰일 = :t"),
            c, params={"t": today_str()})
        # ★차기지표물 [OWNER 2026-09-03 「전반적으로 지표물 확인해보고」]
        #   지표는 분기(3·6·9·12월 10일)마다 갈리는데, 딜러가 실제로 도는 것은
        #   «지정 전에 입찰로 쌓이는 다음 종목» 이다. 2026-09-02 실측: 지표 7종의
        #   호가는 0~1건인데 26-7·26-9·26-10·26-8 이 책의 대부분이었고,
        #   이 넷이 정확히 «그 만기에서 지표물보다 만기일이 늦은 최신 경쟁입찰물» 이다.
        aucall = pd.read_sql(text(
            "SELECT 표준코드, 종목명, 만기 FROM `국채_입찰` "
            "WHERE 구분='경쟁' AND 입찰일 <= :t"),
            c, params={"t": today_str()})
        msb_mst = pd.read_sql(text(
            "SELECT 표준코드, 종목명, 발행일, 만기일, 인포맥스소분류 "
            "FROM `통안채_발행정보` WHERE 만기일 >= CURDATE()"), c)
        # ★통안 최신물은 민평 적재가 며칠 늦는다. 7일 창으로는 모자랐다 —
        #   실측 2026-09-07: 통안 여섯 만기 중 넷(28.04.02·28.07.02·28.09.03·29.03.03)의
        #   마지막 민평이 2026-08-26 에 멈춰 있어, 09-03 기준 7일 창(08-27~)에서
        #   «하루 차이로» 빠졌다. 그 결과 통안 책 61칸 중 44칸(72%)에 레벨이 없었다.
        #   ⚠묵은 민평이라 «전일 민평 대비» 가 아니다 — 엔트리의 mpd(민평 일자)를
        #   화면이 표시한다. 레벨이 아예 없는 것보다 낫다는 판단.
        mp31 = pd.read_sql(text(
            "SELECT t.종목코드, t.민평, t.일자 FROM `국고통_민평` t "
            "JOIN (SELECT 종목코드, MAX(일자) d FROM `국고통_민평` "
            "      WHERE 종목코드 LIKE 'KR31%' "
            "        AND 일자 >= DATE_SUB(:d, INTERVAL :w DAY) GROUP BY 종목코드) x "
            "ON t.종목코드 = x.종목코드 AND t.일자 = x.d"),
            c, params={"d": str(d0), "w": MSB_MP_WIN})
    otr["BondCode"] = otr["종목명"].str.extract(r'\((\d{2}-\d{1,2})\)')
    otr = otr.dropna(subset=["BondCode"])
    # ★물가채(TIPS)는 민평이 «실질금리» 다(0.6~1.8%). 명목 커브에 섞으면 톱니가 된다.
    #   `국채_발행정보` 에는 YY-N 이름으로 안 들어 있고 ontherun 의 «물가…(18-5)» 로 온다.
    _lk = otr.loc[otr["종목명"].astype(str).str.startswith("물가"), "BondCode"]
    linkers = sorted(set(norm_code(_lk))) if len(_lk) else []
    iss = iss.rename(columns={"종목명": "BondCode"})
    m = pd.concat([otr[["BondCode", "표준코드"]], iss[["BondCode", "표준코드"]]])
    m["BondCode"] = norm_code(m["BondCode"])
    m = m.drop_duplicates("BondCode", keep="last")
    j = mp.merge(m, left_on="종목코드", right_on="표준코드")
    out = dict(zip(j["BondCode"], j["민평"]))
    mm = m.merge(mats, on="표준코드", how="left")
    matmap = {r.BondCode: str(r.만기일)[:10] for r in mm.itertuples()
              if pd.notna(r.만기일)}
    # 연물: 국채_발행정보 인포맥스소분류('10Y')를 소문자로. 지표물: 만기별 마지막 지정.
    tenmap = {r.BondCode: str(r.인포맥스소분류).lower()
              for r in mm.itertuples() if pd.notna(r.인포맥스소분류)}
    # 정식표기: ontherun 의 «국고02750-2812(25-10)» 우선, 없으면 쿠폰·만기로 구성
    namemap = {}
    onames["code"] = onames["종목명"].str.extract(r"[(](\d{2}-\d{1,2})[)]")
    for r in onames.dropna(subset=["code"]).itertuples():
        namemap[norm_code(pd.Series([r.code]))[0]] = str(r.종목명)
    for r in mm.itertuples():
        if r.BondCode in namemap or pd.isna(r.표면이율) or pd.isna(r.만기일):
            continue
        cpn = f"{int(round(float(r.표면이율) * 1000)):05d}"
        ym = str(r.만기일)[2:4] + str(r.만기일)[5:7]
        namemap[r.BondCode] = f"국고{cpn}-{ym}({r.BondCode})"
    bench["code"] = bench["종목명"].str.extract(r"[(](\d{2}-\d{1,2})[)]")
    bench = bench.dropna(subset=["code"])
    bench["code"] = norm_code(bench["code"])
    bten = bench.sort_values("일자").groupby("만기")["code"].last()
    bset = list(bten)
    # 차기지표물: 만기별로 «지표물보다 만기일이 늦은» 경쟁입찰 종목 중 최신
    aucall["code"] = norm_code(
        aucall["종목명"].str.extract(r"[(](\d{2}-\d{1,2})[)]")[0].fillna(""))
    aucall["만기"] = pd.to_numeric(aucall["만기"], errors="coerce")
    aucall["matd"] = aucall["code"].map(matmap)
    nxt = {}
    for tn, bc in bten.items():
        bm = matmap.get(bc)
        if bm is None:
            continue
        g = aucall[(aucall["만기"] == float(tn)) & aucall["matd"].notna()
                   & (aucall["matd"] > bm)]
        if len(g):
            nxt[str(float(tn))] = g.sort_values("matd")["code"].iloc[-1]
    nset = sorted(set(nxt.values()))
    log(f"[지표] 지표물 {len(bset)}종 · 차기지표 {len(nset)}종 {nset}")
    # 통안: 마스터(생존)와 민평(KR31)
    msb_mst["발행일"] = pd.to_datetime(msb_mst["발행일"])
    msb_mst["만기일"] = pd.to_datetime(msb_mst["만기일"])
    mp31map = dict(zip(mp31["종목코드"], mp31["민평"]))
    # ★통안 최신물은 민평 적재가 며칠 늦다(7일 폴백). 그래서 «전일 민평 대비» 가
    #   실은 «며칠 전 민평 대비» 일 수 있다. 값을 고치지 말고 날짜를 같이 준다.
    mp31date = {c: str(d)[:10] for c, d in zip(mp31["종목코드"], mp31["일자"])}
    log(f"[민평] {d0} 기준 국고 {len(out)}·통안 {len(mp31map)}종 "
        f"(만기 {len(matmap)}·연물 {len(tenmap)}·지표 {len(bset)}·통안마스터 {len(msb_mst)})")
    aucd = None
    if len(auc):
        r0 = auc.iloc[0]
        bc = re.search(r"[(](\d{2}-\d{1,2})[)]", str(r0["종목명"]))
        aucd = {"code": str(r0["표준코드"]), "name": str(r0["종목명"]),
                "bc": (norm_code(pd.Series([bc.group(1)]))[0] if bc else None),
                "tenor": (float(r0["만기"]) if pd.notna(r0["만기"]) else None),
                "won": (float(r0["낙찰금리"]) if pd.notna(r0["낙찰금리"]) else None),
                "n": len(auc)}
        log(f"[입찰] 오늘({today_str()})은 국채 입찰일 — {aucd['name']} "
            f"{aucd['tenor']}Y · 종목 {len(auc)}건")
    return {"mp": out, "date": str(d0), "mats": matmap, "tenors": tenmap,
            "names": namemap, "bench": bset, "nextbench": nset, "linkers": linkers, "msb_mst": msb_mst, "mp31": mp31map, "mp31date": mp31date,
            "auction": aucd}


# ───────────────────────────────────── 등급별 민평 매트릭스 (아침 1회)
# ★[OWNER 2026-09-03] 「크레딧 매트릭스에서 각 회사채라던가 그거 기준은 대표 신용등급으로」
#   `sim_portfolio.credit_matrix` — bas_dt 2020-01-02~2026-09-02, 매일 적재, 12종 x 13테너.
#   (infomax.matrix_* 8장은 2026-01-23 에서 멈춰 있어 쓰지 않는다.)
#   bond_type 해독은 «로제타석»: 같은 날 infomax.matrix_* 와 대조해 네 날짜(2024-03-15 ·
#   2025-06-10 · 2025-11-20 · 2026-01-23) 전부 **평균절대차 0.00bp** 로 확정했다.
#     KTB=국고채권 · MSB=통안채(이표) · SPB=공사_공단채AAA · KDB=산금채(이표)AAA ·
#     BD=은행채AAA · CARD=카드채AA+ · OFB=기타금융채AA-(=카드채AA-) ·
#     CB1~CB5=회사채공모_무보증 AAA / AA+ / AA0 / AA- / A+
#   화면의 종별 대표 등급(히트맵 HMROWS 와 같은 규약)이 정확히 이 12종에 대응한다.
#   ⚠ 지방채는 이 표에 없다 — 지방채 버킷은 매트릭스 선을 긋지 않고 문면 민평만 쓴다.
MTX_TENORS = {"rt_3m": 0.25, "rt_6m": 0.5, "rt_9m": 0.75, "rt_1y": 1.0, "rt_18m": 1.5,
              "rt_2y": 2.0, "rt_30m": 2.5, "rt_3y": 3.0, "rt_5y": 5.0, "rt_7y": 7.0,
              "rt_10y": 10.0, "rt_20y": 20.0, "rt_30y": 30.0}
MTX_LABEL = {"KTB": "국고채권", "MSB": "통안채", "SPB": "공사채 AAA", "KDB": "특은채 AAA",
             "BD": "은행채 AAA", "CARD": "카드채 AA+", "OFB": "여전채 AA-",
             "CB1": "회사채 AAA", "CB2": "회사채 AA+", "CB3": "회사채 AA0",
             "CB4": "회사채 AA-", "CB5": "회사채 A+"}


def load_matrix_latest():
    """{date, curves: {bond_type: [[잔존년, 금리], ...]}, label} — 최신 bas_dt 한 벌.
    0.000 은 결측이다(장기 구간에 자주 있다) — 버린다. 실패하면 None."""
    from sqlalchemy import text
    try:
        with engine().connect() as c:
            df = pd.read_sql(text(
                "SELECT * FROM sim_portfolio.credit_matrix "
                "WHERE bas_dt = (SELECT MAX(bas_dt) FROM sim_portfolio.credit_matrix)"), c)
    except Exception as e:                               # noqa: BLE001
        log(f"[매트릭스] 로드 실패: {type(e).__name__}: {e}")
        return None
    if not len(df):
        return None
    curves = {}
    for r in df.itertuples():
        pts = [[t, float(getattr(r, k))] for k, t in MTX_TENORS.items()
               if getattr(r, k, None) is not None and float(getattr(r, k) or 0) > 0]
        if pts:
            curves[str(r.bond_type)] = sorted(pts)
    d = str(df["bas_dt"].iloc[0])[:10]
    log(f"[매트릭스] sim_portfolio.credit_matrix {d} · {len(curves)}종 "
        f"({'·'.join(sorted(curves))})")
    return {"date": d, "curves": curves, "label": MTX_LABEL}


# ───────────────────────────────────────────── 꼬리 읽기
class Tail:
    """파일별 바이트 오프셋을 기억하고 새로 붙은 조각만 돌려준다."""

    def __init__(self):
        self.pos: dict[Path, int] = {}
        self.buf: dict[Path, str] = {}

    def today_files(self):
        ymd = REPLAY or date.today().strftime("%Y%m%d")
        for room in ROOMS:
            for p in sorted(Path(SRC_DIR).glob(f"채권_{room}_{ymd}_*.txt")):
                yield room, p

    def read_new(self):
        chunks = []
        for room, p in self.today_files():
            try:
                size = p.stat().st_size
            except OSError:
                continue
            start = self.pos.get(p, 0)
            if size <= start:
                continue
            with open(p, "rb") as f:
                f.seek(start)
                raw = f.read(size - start)
            self.pos[p] = size
            txt = self.buf.get(p, "") + raw.decode("cp949", errors="replace")
            # 마지막 줄이 잘렸을 수 있다 — 개행까지만 처리하고 나머지는 버퍼에
            cut = txt.rfind("\n")
            if cut < 0:
                self.buf[p] = txt
                continue
            self.buf[p] = txt[cut + 1:]
            chunks.append((room, txt[:cut]))
        return chunks


# ───────────────────────────────────────────── 책 접기
# ★[2026-09-09] 본문 머리 발행사 추정기(RE_LEAD_DATE·RE_ISSUER·issuer_guess)는
#   `kbond_issuer` 로 옮겼다 — 원장(parse_kbond_logs)도 같은 것을 써야 하는데
#   kbond_live 는 parse 를 import 하므로 거꾸로는 못 부른다.
from kbond_issuer import (RE_ISSUER, RE_LEAD_DATE, issuer_guess,   # noqa: E402,F401
                          issuer_of)


# 종별 분류 — 발행사 이름의 키워드 규칙. 순서가 우선순위다(여전채가 은행채보다 앞:
# «시은계 캐피탈» 은 여전채).
# ★[OWNER 2026-09-03] 크레딧 6분류: 지방채 · 공사채 · 특은채 · 은행채 · 여전채 · 회사채.
#   증권채는 회사채에 넣는다(오너 결정). 순서가 곧 우선순위다 —
#   «산업은행»·«농협은행» 은 «은행» 보다 먼저 특은채에 걸려야 하고,
#   «도시공사»·«교통공사» 는 «공사» 보다 먼저 지방채에 걸려야 한다.
#   2026-09-02 전량 분류 실측: 회사 861 · 여전 758 · 은행 462 · 특은 359 ·
#   공사 313 · 지방 252 (미분류 0).
_SECTOR_RULES = [
    # ★[OWNER 2026-09-10] 유동화 — 7번째 계열. 맨 앞에 둔다(캐피탈·은행 어간이
    #   SPC 이름 안에 살기 때문: 케이카캐피탈제사차유동화전문 · 국민챔피온제이십차).
    #   ⚠이름으로 가릴 수 있는 건 «유동화»·«ABCP» 가 이름에 박힌 것뿐이다.
    #     「제N차」만 있는 SPC(한솔제십오차·마인블루제일차)는 여기서 못 잡는다 —
    #     그건 `classify_issuer` 가 벤더 표를 보고 잡는다.
    ("유동화", (r"유동화", r"ABCP", r"abcp", r"Abcp")),
    # ★[2026-09-09 4차] 부분문자열 -> **앵커 붙인 정규식**. 이유는 위 주석 참조.
    #   `$`(이름 끝)·`^`(이름 시작)이 남의 이름 안에 사는 것을 원천봉쇄한다.
    # ⚠ 꼬리에 «코리아»·«서비스» 가 더 붙는 회사가 있다(오릭스캐피탈코리아 ·
    #   알씨아이파이낸셜서비스코리아) — 벤더 표와의 대조가 잡아 줬다.
    ("여전채", (r"캐피탈(?:코리아)?$", r"카드$", r"할부금융", r"리스$", r"커머셜$",
               r"에프앤아이$", r"파이낸셜(?:서비스(?:코리아)?)?$", r"파이낸스$")),
    # ★[OWNER] 특은채는 셋뿐이다 — 산금·중금·수은. 이름을 통째로 적는다.
    ("특은채", (r"^한국산업은행$", r"^KDB산업은행$", r"^IBK기업은행$",
               r"^중소기업은행$", r"^한국수출입은행$")),
    ("지방채", (r"도시공사$", r"교통공사$", r"도시개발공사$", r"도시철도공사$",
               r"도시관리공사$", r"시설관리공단$", r"개발공사$", r"주택도시공사$",
               r"특별시$", r"광역시$", r"^전주시$",
               # ⚠ «도$» 로 쓰면 HL만**도** 가 지방채가 된다(대조가 잡았다).
               #   광역자치단체는 이름을 통째로 적는다.
               r"^경기도$", r"^강원도$", r"^강원특별자치도$", r"^제주도$",
               r"^제주특별자치도$", r"^충청북도$", r"^충청남도$", r"^전라북도$",
               r"^전북특별자치도$", r"^전라남도$", r"^경상북도$", r"^경상남도$")),
    # ★[OWNER] 농업협동조합중앙회·수산업협동조합중앙회는 공사채.
    ("공사채", (r"^농협중앙회$", r"^수협중앙회$", r"^농업협동조합중앙회$",
               r"^수산업협동조합중앙회$", r"발전$", r"수력원자력$",
               r"공사$", r"공단$", r"^한국전력", r"지역난방", r"^한국가스공사$",
               r"주택금융공사", r"예금보험공사$", r"장학재단$", r"자산관리공사$",
               r"무역보험공사$", r"관광공사$", r"농어촌공사$", r"환경공단$",
               r"항만공사$", r"공항공사$", r"진흥원$", r"진흥공단$", r"진흥공사$",
               r"^외국환평형기금", r"^재정증권$")),
    # ⚠ «뱅크$» 는 현대오일**뱅크** 를 문다(대조가 잡았다).
    ("은행채", (r"은행$", r"금융지주$", r"^신한지주$", r"(?<!오일)뱅크$",
               r"^SC제일은행$")),
]
# ★벤더 분류와의 «독립 대조» — `kbond_sector.py` 가 표를 굽고 어긋난 자리를 센다.
#   규칙을 고칠 때마다 돌려서 «다음 부산은행» 을 사람이 아니라 대조가 찾게 한다.


def _sector_by_rule(n):
    for sec, pats in _SECTOR_RULES:
        for rx in pats:
            if re.search(rx, n):
                return sec
    return "회사채"

# 화면·버킷 정렬 순서 = 위험순 [OWNER 2026-09-10]. 정의는 RISK_ORDER 아래.


# ★[OWNER 2026-09-10] 유동화 축만 «표» 가 정한다. 나머지 여섯은 규칙 그대로다.
#   왜 여기만 표를 보나 — 유동화는 이름으로 못 가린다. 한솔제십오차·마인블루제일차·
#   국민챔피온제이십차 어디에도 «유동화» 가 안 적혀 있다. 반대로 표를 여섯 축 전부에
#   쓰면 안 된다: 발전 5사·도시공사·에프앤아이는 데스크 관례가 벤더를 이긴다
#   (`kbond_sector` 독스트링 참조). 그래서 «유동화면 유동화» 만 덧댄다.
#   ⚠표가 없으면 조용히 규칙으로 돌아간다 — 새 클론에서 kbond_sector.py 를 안 구우면
#     유동화가 통째로 회사채가 된다.
_ABS_TABLE = set()
try:
    _ABS_TABLE = {k for k, v in json.loads(
        (Path(__file__).parent / "kbond_sector.json").read_text(encoding="utf-8")
    ).items() if v == "유동화"}
except OSError:
    pass


# ★[OWNER 2026-09-10] **계열을 위험순으로 바꾼다.** 「국고통안공사는 무위험」.
#
#     무위험   국고 · 통안 · 공사채 · 지방채 · 국민주택 · 국고이자채 · 물가채
#     특은채   산금 · 중금 · 수은
#     은행채
#     카드채   여전채 중 카드
#     캐피탈   나머지 여전(캐피탈·할부금융·리스·에프앤아이·파이낸셜)
#     회사채
#     유동화   (2026-09-10 신설 · 칸 유지 [OWNER])
#     MBS     (따로 [OWNER])
#
# ⚠**«발행체 계열»(6/7분류)을 없앤 게 아니다.** 그건 `sector_of` 로 남는다 —
#   벤더 대조(`kbond_sector`)가 그 축으로 견주고, 문면 낱말(「3월 공사채 사자」)도
#   그 낱말을 쓴다. 위험 계열은 **화면·책의 라벨** 이다. 둘을 한 이름으로 부르면
#   대조가 자기 산출을 보게 된다.
RISK_OF = {"지방채": "무위험", "공사채": "무위험",
           "특은채": "특은채", "은행채": "은행채",
           "회사채": "회사채", "유동화": "유동화"}
RISK_ORDER = ["무위험", "특은채", "은행채", "카드채", "캐피탈", "회사채",
              "유동화", "MBS"]
# 화면·버킷 정렬 순서 — 위험순 한 벌만 쓴다(kbond_view.CLSORD 와 같은 값).


def sector_of(name):
    """발행체 계열 — 지방·공사·특은·은행·여전·회사·유동화. **벤더 대조의 축**이다.
    화면에는 이걸 쓰지 않는다(`classify_issuer` 가 위험순으로 옮긴다)."""
    n = str(name)
    if n in _ABS_TABLE:
        return "유동화"
    return _sector_by_rule(n)


def classify_issuer(name):
    """발행체 **정본**의 계열. 라벨(회차·구조가 붙은 것)이 아니라 정본을 줘야 한다 —
    앵커(`$`)가 회차에 막힌다."""
    n = str(name)
    sec = sector_of(n)
    if sec == "여전채":
        # 카드와 캐피탈은 위험이 다르다 [OWNER]. 갈랐던 자리가 이미 있었다(cls2).
        return "카드채" if "카드" in n else "캐피탈"
    return RISK_OF.get(sec, sec)


# ★[OWNER 2026-09-09] `_ALIAS_OFFICIAL` 을 걷어냈다 — `kbond_issuer.OWNER` 로 갔다.
#
# 여기 있던 25항목은 «화면에서만» 접혔고, 원장(`IssuerCanon`)은 다른 표를 썼다.
# 게다가 이 루프는 첫 일치이지 최장 일치가 아니라서 사전 순서가 곧 규칙이었다 —
# 「농중」이 「농중회」보다 앞에 있어 **«농협중앙회회» 3,595행**이 화면에 떠 있었다.
# 이제 접는 자리는 `kbond_issuer.canon_label` 하나뿐이다(층 순서: owner > mp-test > master).

_RATINGS = {}
try:
    _RATINGS = json.loads(
        (Path(__file__).parent / "issuer_ratings.json").read_text(encoding="utf-8"))
except OSError:
    pass
# 공사·은행·지방은 사실상 AAA 계열이라 규칙으로 보강 (문면 등급이 있으면 그쪽 우선)
def rating_lookup(name, sector):
    base = re.match(r"^([가-힣A-Za-z&]+)", str(name))
    r = _RATINGS.get(base.group(1)) if base else None
    if r:
        return r
    if sector in ("공사채", "은행채", "특은채", "지방채"):
        return "AAA"          # 공사·은행·특은·지방은 사실상 AAA 계열
    return None


# ───────────────────────────────────── 한 메시지 -> 다리들 [OWNER 2026-09-03]
# 「한 메세지에 2개 적을 때 한 개가 씹힌다」 — 파서(extract)는 한 줄에 종목이 둘이어도
# 행 하나만 낸다. 게다가 그 행은 이름은 뒷 다리, 만기·민평은 앞 다리인 키메라다.
# 배치 다리표와 같은 분할기(kbond_legs.split_legs)로 갈라 다리마다 따로 먹인다.
#
# ★이 함수가 «한 벌» 이다 — 라이브(_feed_inner)와 검증기(verify_v4)가 같은 것을 쓴다.
#   따로 구현하면 검증이 자기 구현을 검증하게 된다(그 실수를 이미 두 번 했다).
_LEG_ID = ("BondCode", "BondName", "Maturity", "SeriesNo")


def message_legs(body, ymd, d0=None):
    """[(다리 본문, 그 extract), ...]. 다리가 하나면 목록 길이 1.

    ★교체(국고 코드 둘)는 통째로 둔다 — 쪼개면 교체 책이 죽는다.
    ★양면 호가의 뒷면 정체성 상속: «-3원 사자» 처럼 식별자가 하나도 없는 뒤 다리는
      앞 다리와 같은 종목이다(09-02·09-03 실측 49건 전부 그랬다: 「17-7 -1.5원 팔자 /
      -3원 사자」·「메리츠캐피탈283-2 (민 4.202 끝 .49 A+) 팔자 / -10원 사자」).
      종목·민평·끝전만 물려받고 방향·값·수량은 그 다리 것을 쓴다.
      식별자가 하나라도 있으면 다른 종목이므로 상속하지 않는다.
    """
    d = extract(body, ymd) if d0 is None else d0
    if d["Position"] == "SWAP" and len(RE_SWAP_CODE.findall(body)) >= 2:
        return [(body, d)]
    _b, head, parts = split_legs(body)
    if len(parts) < 2:
        return [(body, d)]
    out = []
    anchor = None                      # 마지막으로 «식별자를 가진» 다리
    anchor_text = None
    for p in parts:
        text = f"{head} {p}".strip() if head else p
        dl = extract(text, ymd)
        if dl["MsgType"] == "OTHER" and dl["Position"] is None:
            continue                   # 콜 날짜 같은 꼬리가 다리로 잘린 것
        if dl["Broker"] is None and d["Broker"]:
            dl["Broker"], dl["BrokerKey"] = d["Broker"], d["BrokerKey"]
        if any(dl[k] for k in _LEG_ID):
            anchor, anchor_text = dl, text
        elif anchor is not None:
            for k in _LEG_ID + ("Sector", "MPYield", "MPYieldDB", "TenorLo", "TenorHi",
                                "SectorCat", "RatingCat"):
                if k in dl and not dl[k] and anchor.get(k):
                    dl[k] = anchor[k]
            # 끝전은 앞 다리 본문에만 적혀 있다 — 같은 종목이니 같은 값이다
            dl["_frac_body"] = anchor_text
        out.append((text, dl))
    return out or [(body, d)]


# ───────────────────────────────────── 끝전(민평 단가 소수부) [OWNER 2026-09-03]
# 「ㄱㄱ 끝전까지 깔끔하게 해서 완결성을 가지게」 — v7 사양3 «원은 환산하지 않는다» 를 대체한다.
#
#   실제 민평 대비 단가차(원) = 호가 원 − 끝전
#
# 끝전 = 전일 민평 «단가»(액면 1만원당)의 소수부. 시장은 정수부를 기준으로 원 호가를
# 얹으므로, 같은 «+1원 팔자» 라도 끝전 .92 면 민평보다 0.08원 비싼 것이고 끝전 .11 이면
# 0.89원 비싼 것이다 — 열 배 갈린다. 끝전은 [0,1) 에 고르니 절반이 그렇다.
# 근거: PROMPT_frac_2026-09-03.md §A~§D (본표 820만행 실측).
#   표기 끝전 사용 시 예측−결과금리 |중앙| 0.09bp · p90 0.79bp
#   0.5 가정              |중앙| 0.43bp · p90 2.20bp
#   끝전 무시(0)          |중앙| 0.71bp · p90 3.44bp
FRAC_EST = 0.5              # 끝전 결측 시 가정값 (절사가 [0,1) 균등이므로 기대값)
FRAC_EST_MIN_TTM = 0.75     # 그 가정을 허용하는 최소 잔존(년). §C: 위로는 최대 오차 0.67bp,
                            #   아래는 p90 0.73~6.09bp 라 지어내는 셈이 된다. [OWNER 결정 대상]


def mp_frac(body):
    """(끝전, 출처) — 없으면 (None, None). ★정규식을 새로 쓰지 않는다.

    ★함정(본표 53,595행 사고): 한 갈래짜리 옛 정규식은 '끝전0.4' 의 선행 0 을 먹어
      0.0 을 돌려줬다. 범위검사를 통과하는 «틀린 값» 이라 더 위험했다.
      enrich_kbond_quotes.RE_MP_FRAC 은 두 갈래(소수점형·정수형)라 그 사고가 없다.
    ★적용 문자열은 그 «다리» 의 body 다. 한 줄에 종목이 둘이면 끝전도 둘이다.
    하지 않는 것: 같은 날 상속(후보 12.8%뿐이고 그중 20%는 하루에 값이 둘 이상) ·
      DB 조회(국고통_민평은 수익률뿐) · 결과금리에서 역산(그 행은 이미 Q 단이다).
    """
    m = RE_MP_FRAC.search(str(body))
    if m:
        g = m.group(1) or m.group(2)
        if g is not None:
            v = float("0." + g)
            if 0.0 <= v < 1.0:
                return v, "stated"
    m = RE_LIST_FRAC.search(str(body))       # '(민 2.883%, 0.76원)' 목록형
    if m:
        try:
            v = float(m.group(1))
        except (TypeError, ValueError):
            return None, None
        if 0.0 <= v < 1.0:
            return v, "list"
    return None, None


def today_ts():
    """잔존 계산의 기준일. ★리플레이면 그날이다 — 오늘로 재면 r(bp/원)이 틀어진다."""
    return (pd.Timestamp(f"{REPLAY[:4]}-{REPLAY[4:6]}-{REPLAY[6:]}") if REPLAY
            else pd.Timestamp.today())


def frac_bp(won, frac, ttm):
    """(원 − 끝전) -> 민평 대비 bp. 부호는 won_to_bp 규약(+원 = 단가↑ = 금리↓)."""
    v = won_to_bp(np.array([float(won) - float(frac)]), np.array([float(ttm)]))[0]
    return None if not np.isfinite(v) else round(float(v), 1)


# ───────────────────────────────────── 가림 [OWNER 2026-09-03 「일단 XXX로」]
# 「딜러이름이랑 번호는 일단 XXX로 해두자」 — 밖에 내보내기 전 단계.
#
# ★가림은 «출력 직전» 이 아니라 «책에 넣을 때» 한다. 화면에서 가리면 원본이 이미
#   브라우저까지 간 뒤라 가린 것이 아니다. 여기서 가리면 /book.json·/feed.json·SSE
#   어디에도 실명이 없다.
# ★뭉개지 않고 «구분되는» 라벨을 준다(H01 · H01-2). 하나로 뭉개면 딜러 프로필·
#   최우선 점유·하우스 패널이 통째로 죽는다. 같은 데스크는 언제나 같은 라벨이다.
#   [OWNER 결정 대상] 완전히 하나로 뭉갤지는 물어 둔다.
# ★원문(raw)도 가린다 — 서명 괄호와 본문에 흩어진 전화번호꼴 전부.
MASK = True                 # `--no-mask` 로 끈다(로컬에서 원문을 볼 때)
_MASK_HOUSE = {}            # 실제 하우스 -> 'H01'
_MASK_DESK = {}             # (하우스, 표시명) -> 'H01-2'
_MASK_KEY = {}              # 브로커키 -> 'K041'
# 전화번호꼴: 02-3770-5194 · 3770-5194 · 709 2457 · ☎6188-9657
_RE_TEL = re.compile(r"(?<!\d)(?:0\d{1,2}[-.\s]?)?\d{3,4}[-.\s]?\d{4}(?!\d)")


def mask_house(h):
    if not MASK or not h:
        return h
    lab = _MASK_HOUSE.get(h)
    if lab is None:
        lab = _MASK_HOUSE[h] = f"H{len(_MASK_HOUSE) + 1:02d}"
    return lab


def mask_desk(disp, house):
    """데스크 표시명 -> 'H01-2'. 하우스가 같으면 앞자리가 같다."""
    if not MASK or not disp:
        return disp
    hl = mask_house(house)
    lab = _MASK_DESK.get((hl, disp))
    if lab is None:
        n = sum(1 for k in _MASK_DESK if k[0] == hl) + 1
        lab = _MASK_DESK[(hl, disp)] = f"{hl}-{n}"
    return lab


def mask_key(k):
    """브로커키(전화 한 줄)는 그 자체가 개인 식별자다 — 안정 라벨로 바꾼다."""
    if not MASK or not k:
        return k
    lab = _MASK_KEY.get(k)
    if lab is None:
        lab = _MASK_KEY[k] = f"K{len(_MASK_KEY) + 1:03d}"
    return lab


def mask_raw(body, disp=None, house=None):
    """원문에서 서명 괄호를 라벨로 바꾸고, 남은 전화번호꼴을 지운다."""
    if not MASK or not body:
        return body
    who = mask_desk(disp, house) if disp else "XXX"
    brk, rest = split_broker(body)
    out = f"{rest} [{who}]" if brk is not None else body
    return _RE_TEL.sub("XXX", out)


# ───────────────────────────────────── 하우스 > 데스크 > 딜러 [OWNER 2026-09-03]
# 딜러 = 브로커키(전화 한 줄, 한 사람) · 데스크 = 표시명(«DS투자증권 CM팀») · 하우스 = 회사.
# 하우스는 이름 머리말로 정하되, 2026-07~09 실측(36.4만 행·532키)에서 «한 국번 = 한 회사»
# 인 국번은 전화로 확정한다(«채권금융팀 6923-…» 처럼 이름에 회사가 없는 데스크가 있다).
# ★같은 국번을 여러 회사가 쓰는 곳이 있다(3770 한양/유안타 · 3772 한화/신한 · 3779 상상인/LS
#   · 368 부국/유진 · 3771 교보/하나 · 3774 미래/…) — 그 국번은 이름으로만 간다.
# «케이알 vs 케이프» 처럼 앞 두 글자가 같은 회사는 머리말 전체로 가르므로 섞이지 않는다.
_HOUSE_SUFFIX = re.compile(
    r"(투자증권|증권|자산운용|자산|캐피탈|투자|채권투자팀|채권투자|채권사업실|채권부|채권|"
    r"금융시장실|FICC전략|FICC|FIS|FM|FI|CMS|CM|BTS|BT|MS|채금|채영|채전|멀티|솔루션|종금)+$")
_HOUSE_ALIAS = {
    "디에스": "DS", "흥국종금": "흥국", "KR": "케이알", "아이엠": "iM", "코리아": "코리아에셋",
    "트래디션": "Tradition", "우투": "우리투자", "우리": "우리투자", "미래": "미래에셋",
    "kmb": "KMB", "sk": "SK", "부국채권금융": "부국", "부국금융시장실": "부국",
    "부국채권전략": "부국", "케이프채권전략": "케이프", "메리츠FICC전략": "메리츠",
    "한양중년": "한양", "신한투자채권부": "신한", "서울외국환중개": "서울외국환",
    "흥국S": "흥국", "우투S": "우리투자", "LS": "LS증권", "KR매크로": "케이알",
}
# 이름에 회사가 없을 때 쓰는 국번표 (점유 89% 이상인 국번만)
_HOUSE_EXCH = {
    "709": "DS", "6742": "흥국", "6260": "흥국", "6454": "메리츠", "2009": "리딩",
    "6923": "케이프", "6902": "케이프", "6114": "KB", "6188": "부국", "3773": "SK",
    "772": "KIDB", "771": "KIDB", "6910": "한양", "2090": "케이알", "2168": "케이알",
    "2004": "신영", "6021": "Tradition", "2033": "bgc", "2229": "NH", "768": "NH",
    "2184": "다올", "6915": "IBKS", "3706": "KMB", "369": "DB", "3276": "한투",
    "6099": "카카오페이", "769": "대신", "3215": "BNK", "2115": "BNK", "2020": "삼성",
}
_HOUSE_GENERIC = {"채권금융팀", "채권솔루션", "채권전략", "채권부", "채권", "FICC전략",
                  "채권영업부", "채권영업팀", "채권금융", "채권시장본부", "자본시장본부"}


def house_of(disp, key):
    """(표시명, 브로커키) -> 하우스 이름. 모르면 표시명 머리말 그대로."""
    m = re.match(r"^[\s\[\(【]*([가-힣A-Za-z]+)", str(disp or ""))
    w = m.group(1) if m else ""
    w = _HOUSE_ALIAS.get(w, w)
    w2 = _HOUSE_SUFFIX.sub("", w)
    if len(w2) >= 2:
        w = _HOUSE_ALIAS.get(w2, w2)
    k = str(key or "")
    if (not w or w in _HOUSE_GENERIC or len(w) < 2) and k.isdigit():
        ex = k[:4] if len(k) >= 8 else k[:3]
        w = _HOUSE_EXCH.get(ex, w)
    return w or str(disp or "")[:8]


def tsec(t):
    try:
        h, m, s = str(t).split(":")
        return int(h) * 3600 + int(m) * 60 + int(s)
    except Exception:                                    # noqa: BLE001
        return None


# ───────────────────────────────────── 교체(스위치) 책
# [OWNER 2026-09-03 사양 2] 교체 호가는 «별도 상품» 이다.
#   축 = 신형 − 구형 bp (파서 SpreadSource='swap', 어순과 무관한 «수준»).
#   면 = 신형을 «사는» 쪽이 비드, «파는» 쪽이 오퍼. 오퍼 < 비드 불변식이 그대로 선다
#        (2026-09-03 실측: 비드 -0.3 / 오퍼 -0.5).
#   다리 추출은 파서가 못 한다 — BondCode 에 한 다리만 담긴다. 여기서 둘 다 뽑는다.
RE_SWAP_CODE = re.compile(r'(?<![\d.])(\d{2})\s*-\s*(\d{1,2})(?![\d.])')
RE_SWAP_BUY = re.compile(r'사고|사는|사자|사서|매수|삽니다|\+')
RE_SWAP_SELL = re.compile(r'팔고|팔거나|파는|팔자|팝니다|매도|-')
SWAP_WIN = 16          # 코드 뒤 이 글자수 안에서 동사를 찾는다


def swap_legs(body):
    """(사는 다리, 파는 다리). 코드마다 «그 뒤 가장 가까운 동사» 로 방향을 정하고
    다음 코드 앞에서 멈춘다(남의 동사를 가져오지 않기 위해).
    두 다리가 정확히 하나씩 갈리지 않으면 (None, None) — 지어내지 않는다."""
    ms = list(RE_SWAP_CODE.finditer(body))
    if len(ms) < 2:
        return None, None
    side = {}
    for i, m in enumerate(ms):
        code = norm_code(pd.Series([f"{m.group(1)}-{m.group(2)}"]))[0]
        stop = ms[i + 1].start() if i + 1 < len(ms) else len(body)
        seg = body[m.end():min(stop, m.end() + SWAP_WIN)]
        b = RE_SWAP_BUY.search(seg)
        s = RE_SWAP_SELL.search(seg)
        if b and (not s or b.start() < s.start()):
            side.setdefault(code, "B")
        elif s and (not b or s.start() < b.start()):
            side.setdefault(code, "S")
    buys = [c for c, v in side.items() if v == "B"]
    sells = [c for c, v in side.items() if v == "S"]
    if len(buys) == 1 and len(sells) == 1 and buys[0] != sells[0]:
        return buys[0], sells[0]
    return None, None


def swap_newer(a, b):
    """YY-N 이 큰 쪽이 신형."""
    ka = tuple(int(x) for x in a.split("-"))
    kb = tuple(int(x) for x in b.split("-"))
    return a if ka > kb else b


def uncross_best(entries):
    """무크로스 뒤 최우선 (오퍼, 비드). 화면과 같은 규약 — 오퍼 금리 < 비드 금리,
    크로스 쌍은 오래된 쪽을 지운다."""
    asks = [e for e in entries if e["s"] == "S" and e.get("y") is not None]
    bids = [e for e in entries if e["s"] == "B" and e.get("y") is not None]
    for _ in range(200):
        if not asks or not bids:
            break
        ba = max(asks, key=lambda e: (e["y"], e["t"]))
        bb = min(bids, key=lambda e: (e["y"], -e["t"]))
        if ba["y"] < bb["y"]:
            break
        if ba["t"] <= bb["t"]:
            asks = [e for e in asks if e is not ba]
        else:
            bids = [e for e in bids if e is not bb]
    fa = max(asks, key=lambda e: (e["y"], e["t"])) if asks else None
    fb = min(bids, key=lambda e: (e["y"], -e["t"])) if bids else None
    return fa, fb


def _raw_disp(d, broker):
    """가리기 «전» 표시명 — 원문 서명을 라벨로 바꿀 때만 쓴다."""
    return (re.sub(r"[\d\-~☎().\s]+$", "", str(d["Broker"] or "")).strip()
            or str(broker)[:10])[:12]


def _raw_house(d, broker):
    return house_of(_raw_disp(d, broker), broker)


class Book:
    def __init__(self, ref):
        self.mp = ref["mp"]
        self.mp_date = ref["date"]
        self.mats = ref["mats"]
        self.tenors = ref["tenors"]          # code -> '10y'
        self.names = ref["names"]            # code -> 정식표기
        self.bench = set(ref["bench"])       # 지표물 코드 집합
        self.nextbench = set(ref.get("nextbench") or ())   # 차기지표물
        self.linkers = list(ref.get("linkers") or ())     # 물가채(실질금리)
        self.mp31 = ref["mp31"]              # 통안 ISIN -> 민평
        self.auction = ref.get("auction")    # 오늘 국채 입찰(있으면) — 은어 경고용
        self.mtx = ref.get("mtx")            # 등급별 민평 매트릭스(최신 행) 또는 None
        self.prev = None                     # 어제 책 요약 (백그라운드에서 채운다)
        self.mp31date = ref.get("mp31date", {})   # 통안 ISIN -> 그 민평의 일자
        self.kfills = {}    # code -> {"t","y"}  당일 마지막 체결
        # v12 공격 방향 — 오퍼가 맞았으면 B(사 갔다), 비드가 맞았으면 S(팔았다)
        self.aggr = {"B": 0, "S": 0}
        self.msb = {}       # (dealer,side,key) -> entry  (통안 레인)
        self.mfills = {}    # 통안 key -> {"t","y"}
        # 통안 사다리: 배치 enrich 와 같은 은어 규약 (만기구분 x 발행순위 -> 종목)
        mst = ref["msb_mst"]
        self.msb_ladder = {}                 # (kind, rank) -> (ISIN, 만기일, 종목명)
        self.msb_byname = {}                 # '28.07.02' -> (ISIN, 만기일)
        self.msb_names = {}                  # matd -> 정식표기(마스터 종목명)
        self.msb_kind = {}                   # matd -> 연물('2y')
        self.msb_bench = set()               # 지표(각 만기구분 최근월) matd
        self.msb_alias = {}                  # matd -> 대표 은어 (rank 조합)
        _ALIAS = {("2.0Y", 0): "통당", ("2.0Y", 1): "구통", ("2.0Y", 2): "구구통",
                  ("3.0Y", 0): "삼통", ("3.0Y", 1): "구삼통", ("3.0Y", 2): "구구삼통",
                  ("1Y", 0): "1년물 최근"}
        if len(mst):
            for kind, g in mst.groupby("인포맥스소분류"):
                g = g.sort_values("발행일", ascending=False).reset_index()
                for rank in range(min(len(g), 5)):
                    r = g.loc[rank]
                    matd = str(r["만기일"])[:10]
                    self.msb_ladder[(str(kind), rank)] = (
                        r["표준코드"], matd, str(r["종목명"]))
                    self.msb_names[matd] = str(r["종목명"])
                    self.msb_kind[matd] = str(kind).lower().replace(".0", "")
                    if rank == 0:
                        self.msb_bench.add(matd)
                    a = _ALIAS.get((str(kind), rank))
                    if a:
                        self.msb_alias[matd] = a
            for r in mst.itertuples():
                nm = str(r.종목명).replace("통", "")
                self.msb_byname[nm] = (r.표준코드, str(r.만기일)[:10])
                self.msb_names.setdefault(str(r.만기일)[:10], str(r.종목명))
                self.msb_kind.setdefault(str(r.만기일)[:10],
                                         str(r.인포맥스소분류).lower().replace(".0", ""))
        # ★[OWNER 2026-09-07] 「«관심» 면으로 보이기」 — 종목·방향·딜러·시각은 있는데
        #   레벨만 없는 호가(국고 211,520 · 통안 70,356). 09-01 판정대로 «호가» 로
        #   부르지 않으므로 책(사다리·최우선)에는 안 올린다. 다만 «누가 무엇을
        #   하려는가» 는 정보라 따로 세워 보인다 — 크레딧 매수 바구니와 같은 성격.
        self.axes = {}      # (dealer,side,code) -> 레벨 없는 관심
        self.ktb = {}       # (dealer,side,code) -> entry
        self.credit = {}    # (dealer,label,side) -> entry
        self.baskets = {}   # (dealer,sec,lo,rt) -> entry
        self.swap = {}      # (dealer,face,pair) -> entry  (교체 책)
        # ★v4 국민주택 레인 [OWNER 「좌상단에 국고·통안·국민주택·회사채」]
        #   민평이 DB 에 없다(§SECTOR_RULES 주석). 그래서 축약호가의 **소수부만**
        #   문면 그대로 쓰고, 정수 핸들은 그날 문면에 적힌 국주 민평에서 얻는다.
        #   («민4.304» 같은 행이 오늘 63/145). 기준이 없으면 값을 만들지 않고
        #   축약호가 원문만 보여준다 — 없는 수를 지어내지 않는다.
        self.nhb = {}       # (dealer,side,rung) -> entry
        self.nhb_mp = {}    # rung -> 문면 민평(그 회차 것)
        self.nhb_ref = None  # 은어 사다리(국당·국전…)용 기준 = 오늘 본 최대 문면 민평
        self.nhb_fills = {}  # rung -> {"t","y"}
        self.tape = []      # 구조화된 체결(누가·무엇을·어디서)
        self.n_ack = 0      # 내용 없는 'ㅎㅈ' 확인 응답 수
        # ★v6 메시지 피드 [OWNER 2026-09-03] 「메인화면에 블커본드랑 막무가내가
        #   파싱된게 계속 올라가게」. 모든 메시지를 파싱 결과와 함께 흘린다.
        #   스냅샷에는 꼬리 250건만 싣고(payload), 뷰어가 i 로 이어 붙인다.
        self.stream = []          # 이름 주의: 이 자리를 feed 라 부르면 메서드를 가린다
        self.n_seq = 0
        # ★[OWNER 2026-09-03] 「막무가내랑 블커에 중복되는 게 있어서, 중복은 무시해서
        #   적재」. 실측(2026-09-02 16,291건): 방을 가로지르는 같은 문구가 1,733건
        #   (10.6%)이고 시차 중앙 3초. 같은 방 재게시(436건)는 진짜 재호가라 남긴다.
        #   -> «다른 방 · 20초 안 · 같은 문구» 만 버린다.
        self._recent = {}   # 본문 -> (시각, 방)
        self.n_dup = 0
        self._cur = None    # 지금 접고 있는 메시지의 피드 행 (분기에서 값을 채운다)
        self.n_msg = 0
        self.vnow = 0        # 본 메시지의 최대 시각(초). 리플레이 시계의 기준.
        # ★v8: 표본 행 = [t, mid, 최우선오퍼, 최우선비드, 오퍼딜러수, 비드딜러수,
        #   오퍼심도(억), 비드심도(억)]. 앞 둘은 v4 와 같아 옛 소비자가 그대로 읽는다.
        self.hist = {}      # code -> [[t, mid, ba, bb, nA, nB, dA, dB], ...]  (10초 표본)
        # ★v8 다이나믹스 [OWNER 2026-09-03 「일중 다이나믹스·나이·딜러·체결 매칭」]
        self.pulse = {}     # 10분 버킷 -> {q,a,c,i,o, ktb,msb,nhb,cr,muni,etc}
        self.act = {}       # code -> {버킷 -> [오퍼수, 비드수, 체결수]}
        self.dealers = {}   # k -> 오늘 딜러 통계
        self.atbest = {}    # code -> {k -> [최우선오퍼 초, 최우선비드 초]}
        self._lastT = {}    # code -> 마지막 표본 시각 (at-best 적립용)
        self.events = []    # 이벤트 로그 (first/best/cross/size/fill)
        self._best = {}     # (lane, code) -> (최우선오퍼 y, 최우선비드 y)
        self._seen = set()  # 오늘 처음 본 종목 판정
        self._bq = {}       # k -> 최근 호가 목록 (체결 귀속용)
        self.n_fill_inf = {"level": 0, "prev": 0}
        self.msb_isin = {v[1]: v[0] for v in self.msb_ladder.values()}
        for _nm, (_isin, _matd) in self.msb_byname.items():
            self.msb_isin.setdefault(_matd, _isin)

    # ── v4 헬퍼 ────────────────────────────────────────────────────────
    @staticmethod
    def _disp(d, broker):
        """표시용 딜러명 — 전화번호·괄호 꼬리를 자른다.
        ★[OWNER 2026-09-03] MASK 가 켜져 있으면 여기서 이미 'H01-2' 가 된다.
          하류(책·피드·테이프·이벤트·딜러표)가 전부 이 함수를 거치므로 한 곳이면 된다."""
        raw = (re.sub(r"[\d\-~☎().\s]+$", "", str(d["Broker"] or "")).strip()
               or str(broker)[:10])[:12]
        return mask_desk(raw, house_of(raw, broker)) if MASK else raw

    def _msb_key(self, body, d):
        """통안 은어/종목명 -> (ISIN, 만기일 키). 배치 enrich 와 같은 규약."""
        for w in MSB_ORDER:
            if w in body:
                hit = self.msb_ladder.get(MSB_SLANG[w])
                return (hit[0], hit[1]) if hit else (None, None)
        if d["Maturity"]:
            hit = self.msb_byname.get(str(d["Maturity"]))
            if hit:
                return hit
        return (None, None)

    def _nhb_key(self, body, d):
        """국민주택 사다리 칸. 은어(국당·국전·국전전·국전당) 우선, 없으면 회차."""
        for w in NHB_ORDER:
            if w in body:
                return w
        if d["SeriesNo"]:
            # '23-02' 와 '23-2' 는 같은 회차다 — 정규화하지 않으면 칸이 둘로 갈린다
            return "국주 " + norm_code(pd.Series([str(d["SeriesNo"])]))[0]
        if d["Maturity"]:
            return "국주 " + str(d["Maturity"])
        return None

    def _restore1(self, qr, mpv, absy, at_mp=False):
        """축약호가 한 개를 민평 기준으로 복원. 문면 절대금리가 있으면 그쪽 우선.

        ★[OWNER 2026-09-09] `at_mp` 는 「21-10 민평 팔자」 — 값이 안 적혔지만
          «민평 그 자리» 가 곧 값이다. 09-07 에 크레딧에만 걸었던 처리를 국고·통안으로
          넓힌다(국고 QUOTE 16,135행 · 통안 10,755행이 값 없이 남아 있었다).
          `AtMP` 는 파서가 이미 전 계열에 세워 두었고(국고 94,330 · 통안 7,125행)
          그 뜻은 결과검정으로 확인됐다 — 민평 ±1bp 적중 92.0% 대 기저 40.3%.
          ⚠ 요건상 `AtMP` 는 QuoteRaw·AbsYield·SpreadValue 가 모두 없을 때만 서므로
            앞의 두 갈래와 겹치지 않는다. 그래서 맨 뒤에 둔다.
        """
        if qr is not None and mpv is not None:
            arr, _ = restore(pd.Series([qr]), pd.Series([float(mpv)]))
            if not np.isnan(arr[0]):
                return round(float(arr[0]), 3)
        if absy is not None:
            return round(float(absy), 3)
        if at_mp and mpv is not None:
            return round(float(mpv), 3)
        return None

    def _tape_row(self, room, t, d, body, broker):
        """CONFIRM 을 «누가 · 무엇을 · 어느 방향 · 얼마에» 로 접는다.

        ★v8 체결 귀속 [OWNER 2026-09-03 「체결 매칭 강화 (37% →)」]
        종목이 문면에 없는 체결(21영업일 CONFIRM 6,896건의 57%)을 «그 브로커의
        직전 호가» 에 귀속한다. 규칙과 검증(라벨 있는 2,711건을 미상으로 가정해
        예측한 적중률, m_fill.py 2026-09-03):
          level : 레벨이 적힌 체결 -> 같은 브로커·같은 레벨 호가, 30분 안   99.4%
          prev  : 맨 ㅎㅈ -> 같은 브로커의 직전 호가, 60초 안                92.9%
          60초를 넘으면 귀속하지 않는다 (1~5분 71.6% · 5분+ 40% 아래). 방향 일치 91.3%.
        ★[OWNER] 옛 weak 등급(60~300초)은 뺐다 — 네 건 중 한 건이 틀린 값을 화면에 남기느니
          «내용 없는 ㅎㅈ» 으로 세는 편이 낫다는 판정.
        맨 ㅎㅈ 의 직전 같은-발신자 메시지는 73% 가 호가이고 시차 중앙 6초다.
        """
        sec = d["Sector"]
        k = mask_key(str(broker)[:14])
        lane = code = nm = None
        y = None
        csrc = "stated"
        qe = None                        # 귀속된 호가 (있으면)
        if sec == "국고" and d["BondCode"]:
            lane, code, nm = "ktb", d["BondCode"], d["BondCode"]
            y = self._restore1(d["QuoteRaw"], self.mp.get(code), d["AbsYield"],
                               d["AtMP"])
        elif sec == "통안":
            isin, matd = self._msb_key(body, d)
            if matd:
                lane, code = "msb", matd
                nm = self.msb_names.get(matd, matd)
                y = self._restore1(d["QuoteRaw"], self.mp31.get(isin), d["AbsYield"],
                                   d["AtMP"])
        elif sec == "국민주택":
            code = self._nhb_key(body, d)
            if code:
                lane, nm = "nhb", code
                y = self._restore1(d["QuoteRaw"], d["MPYield"] or self.nhb_ref,
                                   d["AbsYield"])
        elif sec == "크레딧/기타":
            nm = d["BondName"] or issuer_of(body, _raw_disp(d, broker)) or d["Maturity"]
            if nm:
                nm = str(kbond_issuer.canon_label(nm))[:16]
                lane = "cr"
        if code is None and nm is None:
            inf = self._infer_fill(k, t, d)
            if inf is not None:
                lane, code, qe, csrc = inf
                nm = self.msb_names.get(code, code) if lane == "msb" else code
                y = qe.get("y")
                if d["QuoteRaw"] is not None or d["AbsYield"] is not None:
                    ref = (self.mp.get(code) if lane == "ktb" else
                           self.mp31.get(self.msb_isin.get(code)) if lane == "msb" else
                           self.nhb_mp.get(code, self.nhb_ref) if lane == "nhb" else None)
                    yy = self._restore1(d["QuoteRaw"], ref, d["AbsYield"])
                    if yy is not None:
                        y = yy
                self.n_fill_inf[csrc] += 1
                sec = {"ktb": "국고", "msb": "통안", "nhb": "국민주택",
                       "cr": "크레딧/기타"}.get(lane, sec)
        s_ = ("B" if d["Position"] == "BUY" else
              "S" if d["Position"] == "SELL" else None)
        if s_ is None and qe is not None:
            s_ = qe.get("s")
        # ★[OWNER 2026-09-03] 체결 수량은 «직전 그 브로커의 호가» 에서 상속한다.
        #   «26-7 845- 100» 뒤의 «26-7 845- ㅎㅈ» 은 100억이다. 못 찾으면 기본단위.
        amt, asrc = d["AmountEff"], d["AmountSource"]
        if asrc in (None, "default"):
            if qe is not None:
                if qe.get("asrc") not in (None, "default"):
                    amt, asrc = qe["a"], "inherit"
            elif code:
                src = (self.ktb if lane == "ktb" else
                       self.msb if lane == "msb" else
                       self.nhb if lane == "nhb" else {})
                best = None
                for e in src.values():
                    if e.get("code") != code or e.get("k") != k:
                        continue
                    if (y is not None and e.get("y") is not None
                            and abs(e["y"] - y) > 1e-9):
                        continue        # 레벨이 다르면 그 호가의 체결이 아니다
                    if e.get("asrc") in (None, "default"):
                        continue        # 그 호가도 수량이 없었다
                    if best is None or e["t"] > best["t"]:
                        best = e
                if best is not None:
                    amt, asrc = best["a"], "inherit"
        if self._cur is not None:
            self._cur.update({"n": nm, "code": code, "y": y, "a": amt, "asrc": asrc,
                              "s": s_, "csrc": (csrc if code else None)})
        if nm is None and y is None:
            self.n_ack += 1                  # 내용 없는 'ㅎㅈ' 응답 (귀속도 안 됨)
            return
        # ★v12 체결 귀속 [OWNER 2026-09-07 「K-Orderbook++」 → §11 «체결 귀속»]
        #   v8 은 «종목이 없는» 체결만 직전 호가에 붙였다(_infer_fill).
        #   여기서는 «종목이 있는» 체결을 책에 서 있는 엔트리에 붙인다.
        #   ★붙이되 «지우지» 않는다 — RESULT_fill_attribution_2026-09-07.md 참조.
        #   맞은 호가는 대조군보다 «같은 레벨로 다시 서는» 쪽이라, 지우면 틀린다.
        hit = self._attach_fill(lane, code, nm, broker, y, t)
        ag = None
        if hit is not None:
            # 오퍼가 맞았다 = 누가 사 갔다. 장외 책에 없던 «공격 방향» 이다.
            ag = "B" if hit.get("s") == "S" else "S"
            self.aggr[ag] += 1
        # 종목별 «당일 마지막 체결» — 약한 귀속은 레벨로 쓰지 않는다
        if code and y is not None:
            if lane == "ktb":
                self.kfills[code] = {"t": t, "y": y}
            elif lane == "msb":
                self.mfills[code] = {"t": t, "y": y}
            elif lane == "nhb":
                self.nhb_fills[code] = {"t": t, "y": y}
        if code and lane in ("ktb", "msb", "nhb"):
            b = int(t // PULSE_BIN) * PULSE_BIN
            self.act.setdefault(code, {}).setdefault(b, [0, 0, 0])[2] += 1
            self._event(t, "fill", lane, code, nm, s_, y, amt, self._disp(d, broker),
                        {"csrc": csrc, "ag": ag})
        self.tape.append({
            "t": t, "sec": sec or "기타", "lane": lane, "code": code, "n": nm,
            "s": s_, "y": y, "a": amt, "asrc": asrc, "ag": ag,
            "csrc": (csrc if code else None),
            "d": self._disp(d, broker), "k": k,
            "raw": mask_raw(body, _raw_disp(d, broker),
                            _raw_house(d, broker))[:110], "room": room})
        # 하루치 구조화 체결은 수백 건뿐이다(2026-09-02 실측 209건). 자르지 않는다 —
        # 120 으로 두면 오후에 오전 체결이 사라진다.
        self.tape = self.tape[-800:]

    def feed(self, room, sender, tm, body):
        """★v8: 책에 «못 실은» 호가(코드 없는 국고·스프레드 없는 크레딧·교체 등)도
        귀속 목록에 차단자로 남긴다. 딜러의 마지막 호가가 그런 것이면 뒤따르는
        맨 ㅎㅈ 을 그 «앞의» 실린 호가에 붙이면 안 된다(2026-09-02 검증 F4b 3건)."""
        self._booked = False
        self._last_d = None
        self._feed_inner(room, sender, tm, body)
        self._block_unbooked(sender, tsec(tm))

    def _block_unbooked(self, sender, t):
        """v8 차단자 — 직전에 먹인 것(_last_d)이 호가인데 책에 안 실렸으면 남긴다.
        다리가 여럿인 메시지는 _feed_inner 가 다리마다 이걸 부른다(2026-09-03)."""
        d = self._last_d
        if d is None or self._booked:
            return
        if d["Position"] in ("BUY", "SELL", "SWAP") and (
                d["MsgType"] == "QUOTE" or (d["MsgType"] == "AXE" and d["AtMP"])):
            k = mask_key(str(d["BrokerKey"] or d["Broker"] or sender)[:14])
            bq = self._bq.setdefault(k, [])
            bq.append({"t": t, "lane": None, "code": None, "s": None, "y": None,
                       "qr": None, "ay": None, "a": None, "asrc": None, "d": None})
            if len(bq) > 80:
                del bq[:40]

    def _feed_inner(self, room, sender, tm, body):
        t = tsec(tm)
        if t is None:
            return
        if REPLAY_AT is not None and t > REPLAY_AT:
            return                       # 동결 시점 이후는 세지도 먹지도 않는다
        self.n_msg += 1
        key = body.strip()
        prev = self._recent.get(key)
        self._recent[key] = (t, room)
        if prev and prev[1] != room and 0 <= t - prev[0] <= DUP_WIN:
            self.n_dup += 1
            return                       # 다른 방에 방금 온 것과 같은 문구
        if len(self._recent) > 40000:    # 하루치를 넘으면 오래된 것부터 턴다
            for k in list(self._recent)[:10000]:
                del self._recent[k]

        ymd = REPLAY or date.today().strftime("%Y%m%d")
        d = extract(body, ymd)
        self._last_d = d
        if t is not None and t > self.vnow:
            self.vnow = t                      # 리플레이 가상 시계

        # ★[OWNER 2026-09-03 「한 메세지에 2개 적을 때 한 개가 씹힌다」]
        #   한 줄에 종목이 둘이면 파서(extract)는 한 행만 낸다 — 게다가 이름은 뒷
        #   다리, 만기·민평은 앞 다리 것으로 섞인 키메라다('29.8.13 중금채 팔자
        #   (민4.164 …) 32.2.21 에이치디현대오일뱅크131-3 팔자 (민4.653 …)' 이
        #   «오일뱅크·29.8.13·4.164» 한 행이 됐다). 실측 09-03: 다리≥2 메시지
        #   207/6,071 중 교체 130 을 뺀 77건에서 호가 다리 70개 유실(09-02 는 176).
        #   배치 다리표와 같은 분할기(kbond_legs.split_legs)로 다리마다 따로 먹인다.
        #   교체(국고 코드 둘)는 한 상품이라 통째로 둔다 — 쪼개면 교체 책이 죽는다.
        #   «팔자 / 사자» 양면 크레딧 호가는 파서가 SWAP 으로 부르지만 코드가 하나라
        #   여기서 갈려 두 다리(오퍼·비드)로 들어온다(전에는 통째로 버려졌다).
        legs = message_legs(body, ymd, d)
        if len(legs) == 1:
            self._feed_one(room, sender, t, legs[0][0], legs[0][1], body)
            return
        for text, dl in legs:
            self._booked, self._last_d = False, dl
            self._feed_one(room, sender, t, text, dl, body)
            self._block_unbooked(sender, t)      # v8 차단자도 다리마다
        self._last_d = None                      # feed() 의 마무리 호출은 무효

    def _feed_one(self, room, sender, t, body, d, raw):
        """한 다리(종목 하나)를 책·피드·테이프에 먹인다.
        body = 이 다리의 본문(머리말 포함) · d = 그 extract · raw = 원문 전체."""
        side = d["Position"]
        broker = d["BrokerKey"] or d["Broker"] or sender

        # 피드 행을 먼저 만들어 두고, 아래 분기가 값(종목·수익률)을 채운다.
        # 여기서 restore 를 또 부르지 않으려는 것이다.
        self.n_seq += 1
        self._cur = {
            "i": self.n_seq, "t": t, "r": room, "k": d["MsgType"],
            "sec": d["Sector"], "n": None, "code": None,
            "s": ("B" if side == "BUY" else "S" if side == "SELL" else None),
            "y": (round(float(d["AbsYield"]), 3) if d["AbsYield"] is not None else None),
            "atmp": bool(d["AtMP"]),
            "a": d["AmountEff"], "asrc": d["AmountSource"],
            "bp": d["SpreadValue"],
            "d": self._disp(d, broker),
            "raw": mask_raw(raw, _raw_disp(d, broker), _raw_house(d, broker))[:170],
            # ★v8.1 하우스 > 데스크 > 딜러 [OWNER]: 딜러 = 브로커키(전화 한 줄)
            "bk": mask_key(str(broker)[:14]),
            "h": mask_house(_raw_house(d, broker))}
        # 이름만이라도 붙여 둔다(값은 만들지 않는다). 아래 분기가 더 좋은 값을 덮는다.
        # 이게 없으면 AXE·문의·«원» 단위 크레딧 호가가 피드에서 이름 없이 흐른다.
        if d["Sector"] == "국고" and d["BondCode"]:
            # [OWNER 2026-09-03] 「국고02250-2709 말고 그냥 25-6 으로」
            self._cur["code"] = d["BondCode"]
            self._cur["n"] = d["BondCode"]
        elif d["Sector"] == "지방/첨가소화":
            # ★[OWNER 2026-09-03] 「서철 = 서울철도, 경기지역 = 경기도채권」 —
            #   국민주택과 같은 당월·전월 사다리다. 마스터가 없어 종목은 못 정하고
            #   «발행체 + 칸» 까지만 세운다(값은 문면 민평이 있을 때만).
            _iss = next((w for w in ("서도철", "서철", "서울도시철도", "도시철도",
                                     "경기지역", "지역개발", "토지주택", "토주",
                                     "부산교통", "대구도시", "인천교통") if w in body), None)
            _rung = next((w for w in ("전전월", "전월물", "전월", "당월물", "당월",
                                      "당발", "전발") if w in body), None)
            if _iss:
                self._cur["n"] = (_iss + " " + _rung) if _rung else _iss
            else:
                # 사다리 은어가 아닌 지방·첨가물(«토지(용지)24-12») 은 일반 폴백으로
                _lab = d["BondName"] or issuer_of(body, _raw_disp(d, broker)) or d["Maturity"]
                if _lab:
                    self._cur["n"] = str(_lab)[:16]
        elif d["Sector"] == "크레딧/기타":
            lab = d["BondName"] or issuer_of(body, _raw_disp(d, broker)) or d["Maturity"]
            if lab:
                self._cur["n"] = str(kbond_issuer.canon_label(lab))[:16]
        else:
            # CD·CP·MBS 처럼 우리 레인이 아닌 것도 «누가» 는 읽힌다(수협CD·하나CD).
            # 만기 날짜보다 발행체 이름이 낫다.
            lab = d["BondName"] or issuer_of(body, _raw_disp(d, broker)) or d["Maturity"]
            if lab:
                self._cur["n"] = str(lab)[:16]
        self.stream.append(self._cur)
        if len(self.stream) > 24000:         # 하루 1.6만건 — 넉넉히 하루치
            del self.stream[:len(self.stream) - 24000]
        # ★v8 시장 맥박 · 딜러 프로필 (모든 메시지, 중복 제외 뒤)
        self._pulse(t, d["MsgType"], d["Sector"])
        self._dealer(mask_key(str(broker)[:14]), self._cur["d"], d, t)

        if d["MsgType"] == "CONFIRM":
            # ★v4 [OWNER 「누가 뭘 샀다로 구조화」]: 원문을 그대로 흘리지 않고
            #   (시각·딜러·방향·종목·수익률·수량)으로 접는다. 내용 없는 'ㅎㅈ'
            #   응답은 테이프에서 빼고 수만 센다.
            # ★v8: 종목이 없는 체결은 _tape_row 가 직전 호가에 «귀속» 한다. 종목별
            #   체결 레벨(kfills·mfills·nhb_fills)도 거기서 한 곳에 적는다.
            self._tape_row(room, t, d, body, broker)
            return

        # 범주 콜 (매수 바구니)
        if d["TenorLo"] is not None and side == "BUY":
            # 만기 연월 환산은 1/12 배수라 그대로 두면 0.6666… 로 표시된다. 반올림.
            lo = round(d["TenorLo"], 2)
            hi = round(d["TenorHi"], 2) if d["TenorHi"] is not None else None
            disp = self._disp(d, broker)
            self._cur.update({"n": f"{lo}~{hi}년" if hi is not None else f"{lo}년",
                              "sec": d["SectorCat"] or "크레딧/기타"})
            self.baskets[(broker, d["SectorCat"], lo, d["RatingCat"])] = {
                "t": t, "lo": lo, "hi": hi,
                "sec": d["SectorCat"] or "전체", "rt": d["RatingCat"],
                "a": d["AmountEff"], "asrc": d["AmountSource"], "d": disp[:12]}
            return

        # 교체(스위치): 별도 상품의 사다리 [OWNER 2026-09-03 사양 2]
        if side == "SWAP" and d["MsgType"] in ("QUOTE", "AXE"):
            buy, sell = swap_legs(body)
            if buy is None:
                return                       # 두 다리가 안 갈리면 책에 넣지 않는다
            new = swap_newer(buy, sell)
            old = sell if new == buy else buy
            face = "B" if buy == new else "S"     # 신형 매수 = 비드
            lvl = None
            if d["SpreadSource"] == "swap" and d["SpreadUnit"] == "bp":
                lvl = float(d["SpreadValue"])     # 신형 − 구형 bp (부호 있음)
            pair = f"{old}/{new}"
            self.swap[(broker, face, pair)] = {
                "t": t, "s": face, "y": lvl, "pair": pair, "new": new, "old": old,
                "a": d["AmountEff"], "asrc": d["AmountSource"],
                "kind": d["MsgType"],            # QUOTE = 호가, AXE = 관심
                "d": self._disp(d, broker), "k": mask_key(str(broker)[:14])}
            self._cur.update({"n": pair, "code": None,
                              "s": face, "y": None, "bp": lvl})
            return

        # ★«민평에» 행은 값이 없어 AXE 로 분류되지만(09-01 판정) 레벨은 민평이다
        #   [OWNER 2026-09-03]. 책에는 들어와야 한다.
        if side not in ("BUY", "SELL") or (d["MsgType"] != "QUOTE"
                                           and not d["AtMP"]):
            return

        # 통안: 은어 사다리(배치와 같은 규약) 또는 종목 직접 표기
        if d["Sector"] == "통안":
            key = isin = matd = None
            for w in MSB_ORDER:
                if w in body:
                    kind, rank = MSB_SLANG[w]
                    hit = self.msb_ladder.get((kind, rank))
                    if hit:
                        isin, matd, _nm = hit
                        key = matd
                    break
            if key is None and d.get("MSBCode"):
                pass                                     # 파서가 채우면 여기로 (현재 미사용)
            if key is None and d["Maturity"]:
                nm = str(d["Maturity"])
                hit = self.msb_byname.get(nm)
                if hit:
                    isin, matd = hit
                    key = matd
            if key is None:
                return
            mpv = self.mp31.get(isin)
            y = None
            if d["QuoteRaw"] is not None and mpv is not None:
                arr, _ = restore(pd.Series([d["QuoteRaw"]]), pd.Series([mpv]))
                y = None if np.isnan(arr[0]) else round(float(arr[0]), 3)
            if y is None and d["AbsYield"] is not None:
                y = round(float(d["AbsYield"]), 3)
            _atmp = False
            if y is None and d["AtMP"] and mpv is not None:
                y, _atmp = round(float(mpv), 3), True     # 민평에
            entry = {"t": t, "s": "B" if side == "BUY" else "S", "atmp": _atmp,
                     "y": y, "a": d["AmountEff"], "asrc": d["AmountSource"],
                     "d": self._disp(d, broker), "k": mask_key(str(broker)[:14]),
                     "code": key, "mp": mpv,
                     "mpd": self.mp31date.get(isin)}
            if y is not None:
                self.axes.pop((broker, side, key), None)
            self.msb[(broker, side, key)] = self._carry_hit(
                self.msb, (broker, side, key), entry)
            self._after_quote("msb", key, entry, d["QuoteRaw"], d["AbsYield"])
            if y is None:
                self._axis(t, "msb", key, self.msb_names.get(key, key), side, d, broker)
            self._cur.update({"n": self.msb_names.get(key, key), "code": key, "y": y})
            return

        # ★국딱 = «그날 입찰된 국고채». 만기가 아니라 상태다.
        #   2026-09-03 판별검정(RESULT_slang_nhb_auction.md): 그날 입찰물 기준
        #   복원 적중 93.2%(n=4,725), 국민주택 기준은 10.1%. 그리고 국딱은
        #   비입찰일에 한 행도 없다. 코드가 없는 행에만 붙인다 —
        #   '국딱 팔고 24-8 사자' 의 24-8 은 짝 다리지 국딱이 아니다.
        if (d["Sector"] == "국고" and not d["BondCode"] and "국딱" in body
                and self.auction and self.auction.get("bc")):
            d["BondCode"] = self.auction["bc"]

        # 국민주택 1종: 민평이 DB 에 없다. 소수부는 문면 축약호가 그대로 쓰고
        # 정수 핸들만 그날 문면에 적힌 국주 민평에서 얻는다(_resolve_nhb 에서).
        if d["Sector"] == "국민주택":
            key = self._nhb_key(body, d)
            if key is None:
                return
            if d["MPYield"] is not None:
                self.nhb_mp[key] = round(float(d["MPYield"]), 3)
                if self.nhb_ref is None or d["MPYield"] > self.nhb_ref:
                    self.nhb_ref = round(float(d["MPYield"]), 3)
            # ★[OWNER 2026-09-07] 국주도 크레딧과 같은 꼴이 있다 —
            #   «30.9.30 국주1종25-09 (민4.105) 팔자» 처럼 문면 민평만 적고 레벨이 없다.
            #   09-03 AtMP 규칙은 MPYield is None 을 요구해 이걸 못 잡는다(전 이력 35,829행).
            _nhb_atmp = (d["MsgType"] == "QUOTE" and d["MPYield"] is not None
                         and d["AbsYield"] is None and d["QuoteRaw"] is None
                         and d["SpreadValue"] is None and not d["IsInquiry"])
            entry = {
                "t": t, "s": "B" if side == "BUY" else "S",
                "y": (round(float(d["AbsYield"]), 3) if d["AbsYield"] is not None
                      else round(float(d["MPYield"]), 3) if _nhb_atmp else None),
                "qr": d["QuoteRaw"], "atmp": bool(d["AtMP"]) or _nhb_atmp, "a": d["AmountEff"],
                "asrc": d["AmountSource"],
                "mp": (round(float(d["MPYield"]), 3)
                       if d["MPYield"] is not None else None),
                "d": self._disp(d, broker), "k": mask_key(str(broker)[:14]), "code": key}
            self.nhb[(broker, side, key)] = self._carry_hit(
                self.nhb, (broker, side, key), entry)
            self._after_quote("nhb", key, entry, d["QuoteRaw"], d["AbsYield"])
            self._cur.update({"n": key, "code": key,
                              "y": (round(float(d["AbsYield"]), 3)
                                    if d["AbsYield"] is not None else round(float(d["MPYield"]), 3) if _nhb_atmp else None)})
            return

        # 국고: 축약호가를 민평으로 복원, 또는 문면 절대금리
        if d["Sector"] == "국고" and d["BondCode"]:
            y = None
            mp = self.mp.get(d["BondCode"])
            if d["QuoteRaw"] is not None and mp is not None:
                arr, _ = restore(pd.Series([d["QuoteRaw"]]), pd.Series([mp]))
                y = None if np.isnan(arr[0]) else round(float(arr[0]), 3)
            if y is None and d["AbsYield"] is not None:
                y = round(float(d["AbsYield"]), 3)
            # ★[OWNER 2026-09-03] 「레벨이 없으면 민평에 팔겠다는 얘기」
            _atmp = False
            if y is None and d["AtMP"] and mp is not None:
                y, _atmp = round(float(mp), 3), True
            if y is not None:
                entry = {
                    "atmp": _atmp,
                    "t": t, "s": "B" if side == "BUY" else "S", "y": y,
                    "a": d["AmountEff"], "asrc": d["AmountSource"],
                    "d": self._disp(d, broker),
                    "k": mask_key(str(broker)[:14]), "code": d["BondCode"]}
                self.axes.pop((broker, side, d["BondCode"]), None)
                self.ktb[(broker, side, d["BondCode"])] = self._carry_hit(
                    self.ktb, (broker, side, d["BondCode"]), entry)
                self._after_quote("ktb", d["BondCode"], entry, d["QuoteRaw"], d["AbsYield"])
            else:
                self._axis(t, "ktb", d["BondCode"], d["BondCode"], side, d, broker)
            self._cur.update({"n": d["BondCode"], "code": d["BondCode"], "y": y})
            return

        # 크레딧 매도 호가. «원» 단위도 받는다(매도의 65%가 원).
        #   ★[OWNER 2026-09-03] v7 사양3 «환산하지 않는다» 는 폐기. 끝전으로 절사 보정해
        #   환산한다 — 실제 민평 대비 단가차 = 호가 원 − 끝전. 위 mp_frac 주석 참조.
        # ★★[OWNER 2026-09-07] 「민평에 팔자는 건 진짜 민평에 팔자는 거야」
        #   크레딧은 민평을 «기준» 으로 «늘» 적는다 — 그래서 09-03 의 AtMP 규칙이
        #   요구하는 `MPYield is None` 이 크레딧에선 사실상 안 걸렸고(전 이력 118행),
        #   스프레드가 없는 매도 268만 행(크레딧 매도의 67.1%)이 통째로 책 밖에 있었다.
        #   실측: 호가·관심 행 중 «테너+레벨» 이 둘 다 잡히는 비율 48.5% → 89.0%.
        #   레벨이 하나도 없고 문면 민평만 있으면 그건 «민평 그 자리» 의 오퍼다.
        #   ⚠AXE(관심)와 문의는 뺀다 — 그건 재고 표시이지 값을 낸 호가가 아니다.
        _cr_atmp = False
        if (d["Sector"] in CR_LANE and side == "SELL"
                and d["MsgType"] == "QUOTE" and d["MPYield"] is not None
                and d["SpreadValue"] is None and d["SpreadWonAbs"] is None
                and d["AbsYield"] is None and d["QuoteRaw"] is None
                and not d["IsInquiry"]
                and not RE_MP_SIGNED_NOUNIT.search(body)):
            d = dict(d, SpreadValue=0.0, SpreadUnit="bp", SpreadSource="overunder")
            _cr_atmp = True

        if d["Sector"] in CR_LANE and d["SpreadValue"] is not None \
                and d["SpreadUnit"] in ("bp", "원") and side == "SELL" \
                and d["SpreadSource"] in ("sign", "overunder", "nounit"):
            label = d["BondName"] or issuer_of(body, _raw_disp(d, broker))                 or d["Maturity"] or (body.split()[0][:14] if body.split() else "?")
            label = kbond_issuer.canon_label(label)
            # ★[2026-09-09 4차] 계열·등급은 **정본** 으로 매긴다. 라벨에는 회차·구조가
            #   붙어 있어(«한국서부발전60-1») 앵커 붙인 규칙이 안 맞는다.
            _canon = str(kbond_issuer.canon_issuer(label)[0] or label)
            _cls = classify_issuer(_canon)
            ttm = None
            matd = None
            if d["Maturity"]:
                mt = maturity_to_ts(d["Maturity"])
                if pd.notna(mt):
                    ttm = round((mt - today_ts()).days / 365.25, 2)
                    matd = str(mt)[:10]
            # 섹터·등급은 본문에서 직접 읽는다 — 발행체명이 범주 규칙에 걸린다
            # ('하나캐피탈' -> 여전채). 범주 콜 추출기와 같은 사전을 쓴다.
            cat_text = kbond_catcall.RE_BANK_AFFIL.sub("", body)
            cats = [n for n, rx in kbond_catcall.SECTOR_CAT if rx.search(cat_text)]
            rt = None
            m = kbond_catcall.RE_RATING.search(body)
            if m:
                rt = m.group(1) or m.group(2)
            disp = self._disp(d, broker)
            mpq = d["MPYield"]                     # 문면에 적힌 전일민평
            _won = d["SpreadUnit"] == "원"
            frac = frac_src = lvl = chk_bp = None
            if _won:
                # ── 원 행 4단 [PROMPT_frac [2]] — 위에서부터 첫 해당 ──────────
                won = float(d["SpreadValue"])
                frac, frac_src = mp_frac(body)
                if frac is None and d.get("_frac_body"):
                    # 양면 호가의 뒷면 — 끝전은 앞 다리에만 적혀 있다(같은 종목)
                    frac, frac_src = mp_frac(d["_frac_body"])
                _ok = (mpq is not None and ttm is not None and ttm > 0)
                if d["AbsYield"] is not None:
                    # Q: 딜러가 결과금리를 적어 줬다. 그 값이 진실이다 — 바꾸지 않는다.
                    ytm = round(float(d["AbsYield"]), 3)
                    dbp = (round((ytm - float(mpq)) * 100, 1) if mpq is not None else None)
                    lvl = "quoted"
                    if frac is not None and _ok:
                        # 대사용: 우리 환산이 딜러의 결과금리와 얼마나 맞는가.
                        _b = frac_bp(won, frac, ttm)
                        if _b is not None:
                            chk_bp = round((float(mpq) + _b / 100) * 100 - ytm * 100, 2)
                elif _ok and frac is not None:
                    # C: 끝전으로 정확 환산
                    _b = frac_bp(won, frac, ttm)
                    dbp = _b
                    ytm = (None if _b is None else round(float(mpq) + _b / 100, 3))
                    lvl = None if ytm is None else "conv"
                elif _ok and ttm >= FRAC_EST_MIN_TTM:
                    # E: 끝전이 없다. 잔존이 충분히 길 때만 0.5 를 «추정» 으로 쓴다.
                    frac, frac_src = FRAC_EST, "assumed"
                    _b = frac_bp(won, frac, ttm)
                    dbp = _b
                    ytm = (None if _b is None else round(float(mpq) + _b / 100, 3))
                    lvl = None if ytm is None else "est"
                else:
                    # N: 민평·잔존이 없거나, 끝전 없이 잔존이 짧다 -> 레벨 미상 유지
                    ytm = dbp = None
                if lvl is None:
                    frac = frac_src = None      # 값을 못 만들었으면 근거도 남기지 않는다
                bpv = None
            else:
                ytm = (round(float(mpq) + float(d["SpreadValue"]) / 100, 3)
                       if mpq is not None else None)
                dbp = None
                bpv = round(float(d["SpreadValue"]), 1)
            _prev_cr = self.credit.get((broker, label, side))
            self.credit[(broker, label, side)] = {
                "atmp": _cr_atmp,        # 문면에 값이 없어 «민평 그 자리» 로 읽은 것
                "t": t, "s": "S", "n": str(label)[:14], "bp": bpv, "dbp": dbp,
                "unit": ("원" if _won else "bp"),
                # 하류가 하나로 쓸 «민평 대비 bp». 원 행은 문면 금리 기준 Δ 다.
                "bpe": (bpv if bpv is not None else dbp),
                "won": (round(float(d["SpreadValue"]), 2) if _won else None),
                "a": d["AmountEff"], "asrc": d["AmountSource"], "d": disp[:12],
                "k": mask_key(str(broker)[:14]),
                "cls": CR_CLS.get(d["Sector"]) or _cls,
                # 히트맵은 카드채를 여전채(캐피탈)와 갈라 본다 [OWNER]
                # ★[2026-09-10] `cls` 가 이미 카드·캐피탈을 가르므로(위험순) cls2 는
                #   같은 값이 된다. 화면·kbond_view 가 아직 cls2 를 읽어서 남겨 둔다.
                "cls2": CR_CLS.get(d["Sector"]) or _cls,
                "ttm": ttm, "cats": cats,
                # 끝전 환산의 근거 — 화면 배지·툴팁과 verify [F] 가 읽는다
                "frac": frac, "fsrc": frac_src, "lvl": lvl, "chk": chk_bp,
                "rt": rt or rating_lookup(_canon, _cls),
                "rt_src": ("문면" if rt else "집계"), "matd": matd,
                "mp": (round(float(mpq), 3) if mpq is not None else None),
                "ytm": ytm, "y": ytm}
            self._carry_hit_cr((broker, label, side), _prev_cr)
            self._after_quote("cr", str(label)[:14], self.credit[(broker, label, side)],
                              d["QuoteRaw"], d["AbsYield"])
            self._cur.update({"n": str(label)[:16], "y": ytm, "lvl": lvl})

    # ── v8 다이나믹스 헬퍼 ───────────────────────────────────────────
    def _pulse(self, t, mt, sec):
        """시장 맥박: 10분 버킷별 종류·레인 건수."""
        b = int(t // PULSE_BIN) * PULSE_BIN
        p = self.pulse.get(b)
        if p is None:
            p = self.pulse[b] = {"q": 0, "a": 0, "c": 0, "i": 0, "o": 0,
                                 "ktb": 0, "msb": 0, "nhb": 0, "cr": 0, "muni": 0, "etc": 0}
        p[{"QUOTE": "q", "AXE": "a", "CONFIRM": "c", "INQUIRY": "i"}.get(mt, "o")] += 1
        p[LANE_OF.get(sec, "etc")] += 1

    def _dealer(self, k, disp, d, t):
        """딜러 프로필: 오늘 무엇을 얼마나 냈나."""
        ds = self.dealers.get(k)
        if ds is None:
            ds = self.dealers[k] = {"k": k, "d": disp, "n": 0, "q": 0, "b": 0, "s": 0,
                                    "c": 0, "i": 0, "first": t, "last": t,
                                    "lane": {}, "codes": {}}
        ds["n"] += 1
        ds["last"] = max(ds["last"], t)
        ds["first"] = min(ds["first"], t)
        mt = d["MsgType"]
        if mt == "QUOTE" or (mt == "AXE" and d["AtMP"]):
            ds["q"] += 1
            if d["Position"] == "BUY":
                ds["b"] += 1
            elif d["Position"] == "SELL":
                ds["s"] += 1
        elif mt == "CONFIRM":
            ds["c"] += 1
        elif mt in ("AXE", "INQUIRY"):
            ds["i"] += 1
        lane = LANE_OF.get(d["Sector"], "etc")
        ds["lane"][lane] = ds["lane"].get(lane, 0) + 1

    def _event(self, t, kind, lane, code, nm, s, y, a, d, x=None):
        self.events.append({"t": t, "k": kind, "lane": lane, "code": code, "n": nm,
                            "s": s, "y": y, "a": a, "d": d, "x": x})
        if len(self.events) > 800:
            del self.events[:200]

    def _after_quote(self, lane, code, e, qr=None, ay=None):
        """호가가 책에 들어온 직후: 귀속용 기록 · 종목 활동 · 이벤트 판정."""
        self._booked = True
        t, k = e["t"], e["k"]
        bq = self._bq.setdefault(k, [])
        bq.append({"t": t, "lane": lane, "code": code, "s": e.get("s"), "y": e.get("y"),
                   "qr": qr, "ay": ay, "a": e.get("a"), "asrc": e.get("asrc"),
                   "d": e["d"]})
        if len(bq) > 80:
            del bq[:40]
        b = int(t // PULSE_BIN) * PULSE_BIN
        ac = self.act.setdefault(code, {}).setdefault(b, [0, 0, 0])
        ac[0 if e.get("s") == "S" else 1] += 1
        ds = self.dealers.get(k)
        if ds is not None:
            ds["codes"][code] = ds["codes"].get(code, 0) + 1
        nm = (self.msb_names.get(code, code) if lane == "msb" else
              (e.get("n") if lane == "cr" else code))
        first = (lane, code) not in self._seen
        self._seen.add((lane, code))
        if first and lane in ("ktb", "msb"):
            self._event(t, "first", lane, code, nm, e["s"], e.get("y"), e.get("a"), e["d"])
        if (e.get("asrc") in ("stated", "bare", "implied") and e.get("a")
                and e["a"] >= BIG_AMT):
            self._event(t, "size", lane, code, nm, e["s"], e.get("y"), e.get("a"), e["d"])
        if lane not in ("ktb", "msb") or e.get("y") is None:
            return
        src = self.ktb if lane == "ktb" else self.msb
        alive = [x for x in src.values() if x["code"] == code and x.get("y") is not None
                 and t - x["t"] <= TTL_DEFAULT["ktb"]]
        others = [x for x in alive if x is not e]
        # 크로스: 새 호가가 남의 반대편을 뚫었다(= 사실상 치는 호가)
        # ★[OWNER 2026-09-03] «락»(오퍼와 비드가 같은 레벨에서 만남)은 이벤트가 아니다.
        #   22거래일 실측: 락은 하루 907건으로 국고 호가의 40%에 이르고, 그 뒤 5분 체결률
        #   46.8% 가 0.5bp 뚫음 47.0% 와 같다(아무것도 안 닿음 22.3%). 간격 0 에서 꺾이는
        #   것이 없으니 «간격 0인 크로스» 일 뿐 따로 이름 붙일 이유가 없다.
        #   -> CROSS_MIN_BP(0.5bp) 이상 «넘어선» 것만 남긴다.
        if e["s"] == "S":
            ob = [x for x in others if x["s"] == "B"]
            if ob:
                hit = min(ob, key=lambda x: x["y"])
                if (e["y"] - hit["y"]) * 100 >= CROSS_MIN_BP - 1e-9:
                    self._event(t, "cross", lane, code, nm, "S", e["y"], e.get("a"),
                                e["d"], {"vs": hit["y"], "vd": hit["d"]})
        else:
            oa = [x for x in others if x["s"] == "S"]
            if oa:
                hit = max(oa, key=lambda x: x["y"])
                if (hit["y"] - e["y"]) * 100 >= CROSS_MIN_BP - 1e-9:
                    self._event(t, "cross", lane, code, nm, "B", e["y"], e.get("a"),
                                e["d"], {"vs": hit["y"], "vd": hit["d"]})
        fa, fb = uncross_best(alive)
        pa, pb = self._best.get((lane, code), (None, None))
        if not first:
            # 최우선 갱신: 오퍼는 금리가 «올라야»(싸져야), 비드는 «내려야» 개선이다
            if e["s"] == "S" and fa is e and pa is not None and e["y"] > pa + 1e-9:
                self._event(t, "best", lane, code, nm, "S", e["y"], e.get("a"), e["d"],
                            {"prev": pa})
            if e["s"] == "B" and fb is e and pb is not None and e["y"] < pb - 1e-9:
                self._event(t, "best", lane, code, nm, "B", e["y"], e.get("a"), e["d"],
                            {"prev": pb})
        self._best[(lane, code)] = (fa["y"] if fa else None, fb["y"] if fb else None)

    @staticmethod
    def _carry_hit(src, key, entry, lvl="y"):
        """절대값 교체가 체결 표시를 지우지 않게 한다.

        같은 (딜러, 방향, 종목) 을 «같은 레벨» 로 다시 세우면 그 레벨은 여전히
        «오늘 실제로 체결된 레벨» 이다 — 실측에서 맞은 호가가 되세워지는 비율이
        83.6%(대조 40.5%)라 이게 지배적인 경로다. 레벨이 바뀌면 물려주지 않는다.
        """
        old = src.get(key)
        if not old or not old.get("ft"):
            return entry
        a, b = old.get(lvl), entry.get(lvl)
        if a is not None and b is not None and abs(float(a) - float(b)) <= 1e-9:
            entry["ft"], entry["fn"] = old["ft"], old.get("fn", 0)
        return entry

    def _carry_hit_cr(self, key, old):
        """크레딧판 _carry_hit. 레벨축이 «민평 대비 bp»(bpe) 라 따로 둔다."""
        new = self.credit.get(key)
        if not old or not new or not old.get("ft"):
            return
        a, b = old.get("bpe"), new.get("bpe")
        if a is not None and b is not None and abs(float(a) - float(b)) <= 1e-9:
            new["ft"], new["fn"] = old["ft"], old.get("fn", 0)

    def _axis(self, t, lane, code, nm, side, d, broker):
        """레벨 없는 관심을 따로 적는다. 책이 아니라 «누가 무엇을 하려는가» 의 목록이다.

        [OWNER 2026-09-07] 09-01 판정(값이 하나도 없으면 호가라 부르지 않는다)은 그대로 두고,
        종목·방향·딜러·시각만으로도 쓸모가 있으니 보이게만 한다. 최우선·스프레드·사다리
        어디에도 안 들어간다 — 레벨이 없으니 넣을 자리도 없다.
        """
        if code is None or side not in ("BUY", "SELL"):
            return
        self.axes[(broker, side, code)] = {
            "t": t, "lane": lane, "code": code, "n": nm,
            "s": "B" if side == "BUY" else "S",
            "a": d["AmountEff"], "asrc": d["AmountSource"],
            "d": self._disp(d, broker), "k": mask_key(str(broker)[:14])}

    def _attach_fill(self, lane, code, nm, broker, y, t):
        """체결을 책에 서 있는 호가에 붙인다 — 지우지 않고 «맞았다» 고 적기만 한다.

        키는 §11 의 (딜러, 방향, 종목).
          국고·통안·국주 : 같은 종목 · 레벨 일치 · 같은 브로커 우선(없으면 같은 레벨의 남)
          크레딧         : 책이 매도 일변도(99.9%)라 (브로커, 라벨) 로 붙인다
        FILL_LEVEL_WIN(30분) 밖에는 붙이지 않는다 — v8 이 검증한 창 그대로다.

        ★왜 «지우지» 않는가 (RESULT_fill_attribution_2026-09-07.md)
          체결이 맞은 호가는 대조군보다 «같은 레벨로 다시 서는» 쪽이다.
          장외 호가는 수량이 정해진 주문이 아니라 레벨을 내건 상시 표시라,
          한 번 붙었다고 그 레벨이 사라지지 않는다. 지우면 있는 시장을 지운다.
        붙은 엔트리에 ft(마지막 체결 시각)·fn(맞은 횟수) 를 적는다.
        """
        src = {"ktb": self.ktb, "msb": self.msb, "nhb": self.nhb,
               "cr": self.credit}.get(lane)
        if not src:
            return None
        bk = mask_key(str(broker)[:14])
        own = other = None
        if lane == "cr":
            key = str(nm)[:14] if nm else None
            if key is None:
                return None
            for e in src.values():
                if e.get("n") != key or e.get("k") != bk:
                    continue
                if e["t"] > t or t - e["t"] > FILL_LEVEL_WIN:
                    continue
                if own is None or e["t"] > own["t"]:
                    own = e
        else:
            if code is None or y is None:
                return None
            for e in src.values():
                if e.get("code") != code or e.get("y") is None:
                    continue
                if e["t"] > t or t - e["t"] > FILL_LEVEL_WIN:
                    continue
                if abs(e["y"] - y) > 1e-9:
                    continue          # 레벨이 다르면 그 호가의 체결이 아니다
                if e.get("k") == bk:
                    if own is None or e["t"] > own["t"]:
                        own = e
                elif other is None or e["t"] > other["t"]:
                    other = e
        hit = own or other
        if hit is not None:
            hit["ft"] = t
            hit["fn"] = hit.get("fn", 0) + 1
        return hit

    def _infer_fill(self, k, t, d):
        """종목 없는 체결을 «그 브로커의 직전 호가» 에 귀속. (lane, code, 호가, 등급)."""
        hist = self._bq.get(k)
        if not hist:
            return None
        qr, ay = d["QuoteRaw"], d["AbsYield"]
        if qr is not None or ay is not None:
            best = None
            for e in reversed(hist):
                if e["t"] > t:
                    continue
                if t - e["t"] > FILL_LEVEL_WIN:
                    break
                if e.get("code") is None:
                    continue                 # 차단자(못 실은 호가)는 레벨 후보가 아니다
                if qr is not None:
                    if e.get("qr") != qr:
                        continue
                elif e.get("ay") is None or abs(e["ay"] - ay) > 1e-9:
                    continue
                if best is None or e["t"] > best["t"]:
                    best = e
            return (best["lane"], best["code"], best, "level") if best else None
        last = None
        for e in reversed(hist):
            if e["t"] <= t:
                last = e
                break
        if last is None or last.get("code") is None:
            return None                      # 마지막 호가를 못 실었으면 귀속하지 않는다
        gap = t - last["t"]
        if gap <= FILL_PREV_WIN:
            return (last["lane"], last["code"], last, "prev")
        return None

    def _dealers_out(self):
        out = []
        for ds in sorted(self.dealers.values(), key=lambda x: -x["n"])[:120]:
            top = sorted(ds["codes"].items(), key=lambda kv: -kv[1])[:6]
            out.append({**{kk: vv for kk, vv in ds.items() if kk != "codes"},
                        "codes": top, "ncode": len(ds["codes"])})
        return out

    def _fresh_best(self, entries, code, T, win=900):
        """방향별 «가장 최근» 호가의 레벨 (15분 창). CBBT 원칙 — 스테일 극단 배제."""
        fa = fb = None
        for e in entries:
            if e["code"] != code or e.get("y") is None or T - e["t"] > win:
                continue
            if e["s"] == "S" and (fa is None or e["t"] > fa["t"]):
                fa = e
            if e["s"] == "B" and (fb is None or e["t"] > fb["t"]):
                fb = e
        return fa, fb

    def clock(self):
        """지금 몇 시인가(초). 리플레이면 마지막 메시지 시각을 쓴다."""
        if REPLAY:
            return self.vnow
        n = datetime.now()
        return n.hour * 3600 + n.minute * 60 + n.second

    def sample_mid(self, T=None):
        """10초 표본으로 종목별 mid 이력을 쌓는다. ★v4: 국고뿐 아니라 통안·
        국민주택도 표본한다(카테고리마다 시세 차트가 있어야 한다). 종목 키는
        레인끼리 겹치지 않는다(국고 '25-10' · 통안 '2028-04-02' · 국주 '국당').
        T 를 주면 그 시각으로 표본한다 — 기동 시 오늘치를 되감을 때 쓴다.
        ★v8: 최우선 오퍼/비드·딜러 수·심도도 같이 싣고, «누가 최우선에 서 있었나»
        를 초 단위로 적립한다(atbest). mid 정의(최근 호가 기준)는 v4 그대로."""
        T = self.clock() if T is None else T
        for src in (list(self.ktb.values()), list(self.msb.values()),
                    self._resolve_nhb()):
            alive = [e for e in src if T - e["t"] <= 1800 and e.get("y") is not None]
            codes = {e["code"] for e in alive}
            for code in codes:
                rows = [e for e in alive if e["code"] == code]
                ba, bb = uncross_best(rows)
                lt = self._lastT.get(code)
                dt = 0 if lt is None else max(0, min(T - lt, 60))
                if dt:
                    ab = self.atbest.setdefault(code, {})
                    if ba is not None:
                        ab.setdefault(ba["k"], [0, 0])[0] += dt
                    if bb is not None:
                        ab.setdefault(bb["k"], [0, 0])[1] += dt
                self._lastT[code] = T
                fa, fb = self._fresh_best(src, code, T)
                if fa is None or fb is None:
                    continue
                mid = round((fa["y"] + fb["y"]) / 2, 4)
                h = self.hist.setdefault(code, [])
                if not h or T - h[-1][0] >= 10:
                    nA = len({e["k"] for e in rows if e["s"] == "S"})
                    nB = len({e["k"] for e in rows if e["s"] == "B"})
                    dA = round(sum(e.get("a") or 0 for e in rows if e["s"] == "S"))
                    dB = round(sum(e.get("a") or 0 for e in rows if e["s"] == "B"))
                    h.append([T, mid, ba["y"] if ba else None, bb["y"] if bb else None,
                              nA, nB, dA, dB])
                    if len(h) > 2500:
                        del h[:500]

    def _match(self, T):
        """크레딧 매도 <-> 수요 바구니 매칭. 조건: 섹터 겹침 & 잔존 구간(±0.25y 여유)
        & 등급(둘 다 있을 때만 — «이상» 은 서열 비교). 어긋나면 막지 않고 비운 쪽은 통과."""
        sells = [e for e in self.credit.values() if T - e["t"] <= TTL_DEFAULT["credit"]]
        baskets = [e for e in self.baskets.values() if T - e["t"] <= TTL_DEFAULT["credit"]]
        for e in sells:
            e["mb"] = 0
        for b in baskets:
            b["ms"] = 0
            blo = b["lo"] - 0.25
            bhi = (b["hi"] if b["hi"] is not None else b["lo"]) + 0.25
            bsecs = set((b["sec"] or "전체").split("|"))
            brk = rating_rank(b["rt"])
            b_upward = bool(b["rt"] and "이상" in b["rt"])
            best = None
            for e in sells:
                if e["ttm"] is not None and not (blo <= e["ttm"] <= bhi):
                    continue
                if "전체" not in bsecs and e["cats"] and not (bsecs & set(e["cats"])):
                    continue
                if "전체" not in bsecs and not e["cats"]:
                    continue
                erk = rating_rank(e["rt"])
                if brk is not None and erk is not None:
                    if b_upward and erk > brk:
                        continue
                    if not b_upward and erk != brk:
                        continue
                b["ms"] += 1
                e["mb"] += 1
                _eb = e.get("bpe")
                if _eb is not None and (best is None
                                        or _eb < best.get("bpe", 9e9)):
                    best = e
            b["bo"] = ({"n": best["n"], "bp": best.get("bpe"), "y": best.get("ytm")}
                       if best else None)

    def _implied(self, T):
        """교체 호가 + «반대 다리의 실행 가능한 최신 아웃라이트»(CBBT) -> 다른 다리의
        내재 호가. 앵커에 민평을 쓰지 않는다 (2026-09-03 기준 3.5bp 어긋난다).

        S = 신형 − 구형 (bp).  y_old = y_new − S/100,  y_new = y_old + S/100.
          앵커 신형: 구형 내재오퍼 = 신형오퍼 − S_bid   (교체 비드가 신형을 산다)
                     구형 내재비드 = 신형비드 − S_ofr
          앵커 구형: 신형 내재오퍼 = 구형오퍼 + S_ofr
                     신형 내재비드 = 구형비드 + S_bid
        내재는 firm 이 아니다(딜러 둘 · 레그 리스크) — 화면에서 흐리게, Σ 누적 제외.
        """
        out = {}
        byp = {}
        for e in self.swap.values():
            if e["y"] is None or T - e["t"] > TTL_DEFAULT["ktb"]:
                continue
            byp.setdefault(e["pair"], []).append(e)
        kt = list(self.ktb.values())
        for pair, es in byp.items():
            old, new = pair.split("/")
            sw_a, sw_b = uncross_best(es)      # 교체 최우선 오퍼 / 비드
            for anchor, target, sgn in ((new, old, -1.0), (old, new, +1.0)):
                fa, fb = self._fresh_best(kt, anchor, T)
                rows = []
                # 내재 오퍼: 앵커 신형이면 (신형오퍼, 교체비드), 앵커 구형이면 (구형오퍼, 교체오퍼)
                src_o = sw_b if anchor == new else sw_a
                src_b = sw_a if anchor == new else sw_b
                if fa is not None and src_o is not None:
                    rows.append(("S", round(fa["y"] + sgn * src_o["y"] / 100, 4),
                                 fa, src_o))
                if fb is not None and src_b is not None:
                    rows.append(("B", round(fb["y"] + sgn * src_b["y"] / 100, 4),
                                 fb, src_b))
                for s_, y_, anc, sw in rows:
                    a1, a2 = anc.get("a"), sw.get("a")
                    amt = None if (a1 is None or a2 is None) else min(a1, a2)
                    asrc = ("oddlot" if (anc.get("asrc") == "oddlot"
                                         or sw.get("asrc") == "oddlot") else
                            ("default" if "default" in (anc.get("asrc"), sw.get("asrc"))
                             else "stated"))
                    out.setdefault(target, []).append({
                        "s": s_, "y": y_, "a": amt, "asrc": asrc,
                        "pair": pair, "swp": sw["y"], "swd": sw["d"],
                        "anc": anchor, "ancy": anc["y"], "ancd": anc["d"],
                        "t": min(anc["t"], sw["t"])})
        # 실호가와 크로스하면 내재를 지운다 (실호가 우선). 내재끼리도 크로스 0.
        for code, rows in list(out.items()):
            real = [e for e in kt if e["code"] == code and e.get("y") is not None
                    and T - e["t"] <= TTL_DEFAULT["ktb"]]
            ra, rb = uncross_best(real)
            keep = []
            for r in rows:
                if r["s"] == "S" and rb is not None and r["y"] >= rb["y"]:
                    continue
                if r["s"] == "B" and ra is not None and r["y"] <= ra["y"]:
                    continue
                keep.append(r)
            ia = max((r for r in keep if r["s"] == "S"), key=lambda r: r["y"], default=None)
            ib = min((r for r in keep if r["s"] == "B"), key=lambda r: r["y"], default=None)
            if ia is not None and ib is not None and ia["y"] >= ib["y"]:
                keep = [r for r in keep if r is not (ia if ia["t"] <= ib["t"] else ib)]
            out[code] = keep
        return {k: v for k, v in out.items() if v}

    def _resolve_nhb(self):
        """국민주택 축약호가 -> 절대금리. 기준은 그 회차 문면 민평, 없으면 그날
        본 국주 민평의 최댓값(은어 사다리 = 당월·전월물이라 가장 최근 발행분).
        기준이 없으면 값을 만들지 않고 축약호가만 남긴다."""
        out = []
        for e in self.nhb.values():
            y = e["y"]
            src = "문면" if y is not None else None
            if y is None and e.get("atmp"):
                ref = self.nhb_mp.get(e["code"], self.nhb_ref)
                if ref is not None:
                    y, src = round(float(ref), 3), "민평에"
            if y is None and e["qr"] is not None:
                ref = self.nhb_mp.get(e["code"], self.nhb_ref)
                if ref is not None:
                    y = self._restore1(e["qr"], ref, None)
                    src = "복원" if y is not None else None
            out.append({**e, "y": y, "ysrc": src})
        return out

    def snapshot(self):
        T = self.clock()
        self._match(T)
        return {
            "now": f"{T // 3600:02d}:{T % 3600 // 60:02d}:{T % 60:02d}",
            "date": (f"{REPLAY[:4]}-{REPLAY[4:6]}-{REPLAY[6:]}" if REPLAY
                     else datetime.now().strftime("%Y-%m-%d")),
            "replay": bool(REPLAY),
            "mp_date": self.mp_date,
            "n_msg": self.n_msg,
            "ttl_default": TTL_DEFAULT,
            "ktb": list(self.ktb.values()),
            "credit": list(self.credit.values()),
            "baskets": list(self.baskets.values()),
            "tape": self.tape[::-1],
            "n_ack": self.n_ack,
            "n_dup": self.n_dup,
            "dup_win": DUP_WIN,
            "nhb": self._resolve_nhb(),
            "nhb_mp": self.nhb_mp,
            "nhb_ref": self.nhb_ref,
            "nhb_fills": self.nhb_fills,
            "nhb_label": NHB_LABEL,
            "auction": self.auction,
            "swap": list(self.swap.values()),
            "implied": self._implied(T),
            "prev": self.prev,
            # ★스냅샷에는 꼬리만 (푸시마다 하루치를 보낼 수는 없다).
            #   새로고침 직후의 스크롤백은 /feed.json 이 따로 채운다.
            "feed": self.stream[-250:],
            "n_seq": self.n_seq,
            "rooms": list(ROOMS),
            "hist": self.hist,
            "mp": self.mp,
            "kfills": self.kfills, "aggr": dict(self.aggr),
            "axes": list(self.axes.values()),
            "mfills": self.mfills,
            "msb": list(self.msb.values()),
            "msb_mp": {k: v for k, v in
                       ((e["code"], e["mp"]) for e in self.msb.values())
                       if v is not None},
            "msb_mpd": {k: v for k, v in
                        ((e["code"], e.get("mpd")) for e in self.msb.values())
                        if v is not None},
            "bench": sorted(self.bench),
            "nextbench": sorted(self.nextbench),
            "linkers": self.linkers,
            "tenors": self.tenors,
            "names": self.names,
            "msb_names": self.msb_names,
            "msb_bench": sorted(self.msb_bench),
            "msb_kind": self.msb_kind,
            "msb_alias": self.msb_alias,
            "mats": self.mats,
            "stats": {c: {"lo": min(x[1] for x in h), "hi": max(x[1] for x in h),
                          "open": h[0][1], "last": h[-1][1]}
                      for c, h in self.hist.items() if h},
            "n_fill": sum(1 for e in self.tape),
            # ★v8 다이나믹스
            "pulse": self.pulse, "pulse_bin": PULSE_BIN, "act": self.act,
            "dealers": self._dealers_out(), "n_dealer": len(self.dealers),
            "atbest": self.atbest,
            "events": self.events[-240:], "n_event": len(self.events),
            "ttl_evidence": TTL_EVIDENCE, "age_steps": AGE_STEPS,
            "mtx": self.mtx,
            "fill_inf": self.n_fill_inf,
            "fill_win": {"level": FILL_LEVEL_WIN, "prev": FILL_PREV_WIN},
        }


# ───────────────────────────────────── 누가 말을 걸 수 있는가 [배포 레인]
# 이 API 는 Vercel 에 올린 화면이 «보는 사람 브라우저» 로 부른다. 출처가 갈리므로
# 모든 요청이 CORS 를 탄다. sauron-v2 `backend/app/cors.py` 의 규율을 그대로 옮긴다.
#
# ## 왜 `*` 가 아닌가
# Funnel 은 인터넷 공개다. 문턱은 토큰과 CORS 둘뿐이고, `*` 는 그중 하나를 없앤다.
# 문턱이 낮은 것과 없는 것은 다르다.
#
# ## 앞뒤 앵커를 반드시 넣는다
# 아래 셋은 사람 눈에 비슷하고 전부 거절되어야 한다 —
#   https://ibond.vercel.app.evil.com  (뒤에 붙인 도메인)
#   https://evil-ibond.vercel.app      (앞에 붙인 라벨)
#   http://ibond.vercel.app            (평문)
DEV_ORIGINS = ("http://localhost:8301", "http://127.0.0.1:8301",
               "http://localhost:8305", "http://127.0.0.1:8305",
               "http://localhost:3000", "http://127.0.0.1:3000",
               # React 판(kbond-web)의 개발 포트. v2 가 :3200 을 쓰므로 겹치지 않게 :3400.
               "http://localhost:3400", "http://127.0.0.1:3400")
# ★하이픈을 «필수» 로 둔다. 우리 프로젝트의 프로덕션 도메인은 `ibond-theta.vercel.app`
#   이고(Vercel 이 붙인 접미사), 접미사 없는 `ibond.vercel.app` 은 **남의 것이다**
#   (2026-09-03 확인: 200 을 주는 다른 사이트). 그걸 물면 그 사이트가 방문자 브라우저로
#   이 API 를 부를 수 있게 된다 — 토큰이 막긴 하지만 문턱을 하나 헐 이유가 없다.
# ★2026-09-04: 새 React 화면의 Vercel 프로젝트(kbond-web)를 함께 받는다.
#   ⚠ibond 쪽 접미사 요구(`ibond-…`)는 그대로 둔다 — 접미사 없는
#     `ibond.vercel.app` 은 **남의 것**이라 열어 주면 안 된다.
#     kbond-web 은 우리 프로젝트라 접미사 없는 주소도 우리 것이다.
DEFAULT_ORIGIN_REGEX = (
    r"\Ahttps://(ibond-[a-z0-9-]+|kbond-web(-[a-z0-9-]+)?)\.vercel\.app\Z")
# 토큰 · 오리진은 환경변수로 뺀다 — 도메인이 정해지는 날 코드를 고치지 않기 위해서다.
TOKEN = os.getenv("KBOND_TOKEN", "").strip()
_n_401 = {"tok": 0, "origin": 0}


def _allowed_origins():
    """정확히 일치해야 하는 출처. 환경변수는 «더한다»(대체가 아니다) —
    대체로 만들면 배포 도메인을 넣는 순간 로컬이 막히고, 그때 사람은 `*` 로 도망간다."""
    extra = [x.strip().rstrip("/") for x in
             os.getenv("KBOND_ALLOWED_ORIGINS", "").split(",") if x.strip()]
    return list(dict.fromkeys(list(DEV_ORIGINS) + extra))


def _origin_regex():
    return os.getenv("KBOND_ALLOWED_ORIGIN_REGEX", "").strip() or DEFAULT_ORIGIN_REGEX


def origin_allowed(origin):
    """스타렛이 하는 판정과 같은 판정. 시험이 이 함수를 부른다 — 서버를 세우지 않고도
    규칙만 고정할 수 있어야 한다."""
    if not origin:
        return False
    if origin.rstrip("/") in _allowed_origins():
        return True
    return re.compile(_origin_regex()).match(origin) is not None


def token_ok(query_token):
    """KBOND_TOKEN 이 없으면 검사하지 않는다(로컬 전용 개발 그대로).
    ★쿼리로 받는 이유: EventSource 는 커스텀 헤더를 못 싣는다. 네 요청이 전부 헤더 없는
      단순 GET 이 되어 프리플라이트도 없다. 대가는 프록시 접근로그에 토큰이 남을 수
      있다는 것 — 이 규모에서는 받아들인다. 값은 우리 로그에 절대 남기지 않는다."""
    if not TOKEN:
        return True
    return bool(query_token) and hmac.compare_digest(str(query_token), TOKEN)


# ───────────────────────────────────────────── 서버
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _cors(self):
        """오리진 에코 + Vary. ★SSE 는 스트림이라 헤더를 나중에 못 붙인다 —
        `end_headers()` 앞에서 반드시 불러야 한다."""
        o = self.headers.get("Origin")
        if not o:
            return
        if origin_allowed(o):
            self.send_header("Access-Control-Allow-Origin", o)
            self.send_header("Vary", "Origin")
        else:
            _n_401["origin"] += 1
            log(f"[CORS 거절] {str(o)[:80]}")

    def _deny(self):
        _n_401["tok"] += 1
        self.send_response(401)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send(self, body, ctype, cache="no-store"):
        """★gzip [2026-09-03 감사]: 스냅샷이 807KB 다. 로컬에선 티가 안 나지만
        테일넷·Funnel 로 나가면 SSE 가 바뀔 때마다 이걸 통째로 민다.
        gzip 하면 86KB(89% 절감)라, 밖으로 내보내기 전에 반드시 켜야 한다."""
        enc = None
        if len(body) > 4096 and "gzip" in (self.headers.get("Accept-Encoding") or ""):
            body, enc = gzip.compress(body, 6), "gzip"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self._cors()
        if cache:
            self.send_header("Cache-Control", cache)
        if enc:
            self.send_header("Content-Encoding", enc)
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        # 쿼리 파싱을 한 곳에서 (토큰·필터가 같은 것을 본다)
        _q = {}
        if "?" in self.path:
            from urllib.parse import unquote as _uq
            for kv in self.path.split("?", 1)[1].split("&"):
                k, _, v = kv.partition("=")
                _q[k] = _uq(v)
        # ★문턱 밖에 두는 것 둘 — 비밀은 «데이터» 이지 «화면» 이 아니다.
        #   /health : Funnel 이 살아 있는지 밖에서 보려면 필요하다. 토큰이 없으면
        #             {"ok":true} 만 준다(상세는 토큰이 맞을 때).
        #   /       : HTML 한 장. 이걸 막으면 로컬에서 화면 자체가 안 뜬다(2026-09-03
        #             실측: 토큰을 켠 순간 http://127.0.0.1:8301/ 이 401 이 됐다).
        #             Vercel 에 올린 같은 파일도 누구나 받는다 — 막을 이유가 없다.
        _open = (self.path.startswith("/health")
                 or self.path.split("?")[0] in ("/", "/index.html"))
        if not _open and not token_ok(_q.get("t")):
            self._deny()
            return
        if self.path.startswith("/events"):
            # SSE — 책이 바뀔 때만 스냅샷을 민다. 15초 유휴면 핑.
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self._cors()
            self.send_header("Cache-Control", "no-store")
            # 프록시가 SSE 를 모아 두면 화면 전체가 멎는다 — 버퍼링 끄기를 요청한다.
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            sent = -1
            try:
                while True:
                    with COND:
                        if STATE["ver"] == sent:
                            COND.wait(timeout=5)
                    with STATE["lock"]:
                        ver, raw = STATE["ver"], STATE["raw"]
                    if ver != sent:
                        self.wfile.write(b"data: " + raw + b"\n\n")
                        sent = ver
                    else:
                        # ★v2: «: ping» 주석은 EventSource.onmessage 에 안 잡혀
                        # 클라이언트가 조용한 구간마다 «연결 끊김» 을 깜빡였다.
                        # 실제 이벤트(hb)로 보낸다 — 시계와 생존 신호를 겸한다.
                        hb = json.dumps({"now": datetime.now().strftime("%H:%M:%S"),
                                         "ver": ver}).encode()
                        self.wfile.write(b"event: hb\ndata: " + hb + b"\n\n")
                    self.wfile.flush()
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
                return
        elif self.path.startswith("/health"):
            if token_ok(_q.get("t")):
                up = time.time() - STATE["t0"]
                d = {"ok": True, "uptime_s": round(up), "ver": STATE["ver"],
                     "last_event_age_s": round(time.time() - STATE["last_evt"], 1)
                                         if STATE["last_evt"] else None,
                     "masked": MASK, "denied": dict(_n_401)}
            else:
                d = {"ok": True}          # 문턱 밖에서는 «살아 있다» 만
            body = json.dumps(d).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/book.json"):
            with STATE["lock"]:
                body = STATE["raw"]
            self._send(body, "application/json; charset=utf-8")
        elif self.path.startswith("/feed.json"):
            # [OWNER 2026-09-03] 「새로고침할 때마다 메인 메시지 수가 준다」 —
            # 스크롤백이 브라우저에만 있었다. 하루치를 서버가 들고 여기서 준다.
            q = _q
            try:
                since = int(q.get("since", 0))
            except ValueError:
                since = 0
            try:
                limit = max(1, min(int(q.get("limit", 4000)), 24000))
            except ValueError:
                limit = 4000
            with STATE["lock"]:
                # 얕은 복사를 먼저 뜬다 — 폴링 스레드가 같은 리스트에 붙이고 자른다
                st = list(STATE["stream"])
            # ★v8.1 [OWNER 「채팅 누르면 그 하우스 딜러가 오늘 낸 호가 · 하우스>데스크>딜러」]
            #   h= 하우스 · d= 데스크(표시명) · k= 딜러(브로커키)
            for kk, fld in (("h", "h"), ("d", "d"), ("k", "bk")):
                if q.get(kk):
                    st = [e for e in st if e.get(fld) == q[kk]]
            rows = [e for e in st if e["i"] > since][-limit:]
            n_seq = st[-1]["i"] if st else 0
            body = json.dumps({"feed": rows, "n_seq": n_seq},
                              ensure_ascii=False).encode("utf-8")
            self._send(body, "application/json; charset=utf-8")
        elif self.path in ("/", "/index.html"):
            self._send(VIEWER.read_bytes(), "text/html; charset=utf-8", cache=None)
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def log_message(self, *a):                           # 콘솔 소음 억제
        pass


# ───────────────────────────────────── 어제 책 (메뉴 씨앗)
# [OWNER 2026-09-03] 「어제 거래됐던 국고나 통안 같은 건 좀 띄워놓으면 안되나
#  일단 메뉴창에」 — 아침에는 오늘 호가가 몇 건뿐이라 메뉴가 비어 있다.
#  어제 로그를 같은 파이프라인으로 한 번 접어 «어제 종가 수준» 을 씨앗으로 둔다.
#  실측 8.5초라 서빙을 막지 않고 백그라운드에서 접고, 결과는 캐시한다.
PREV_DIR = Path(r"C:\Users\infomax\Projects\data\kbond")


def last_log_day():
    """오늘보다 앞선 가장 최근 로그 날짜(YYYYMMDD). 없으면 None."""
    today = REPLAY or date.today().strftime("%Y%m%d")
    days = set()
    for p in Path(SRC_DIR).glob("채권_*_*.txt"):
        m = re.search(r"_(\d{8})_", p.name)
        if m and m.group(1) < today:
            days.add(m.group(1))
    return max(days) if days else None


def prev_summary(ref, ymd):
    """어제 책을 접어 종목별 «마지막 오퍼·비드·mid·체결·건수» 만 남긴다."""
    b = Book(ref)
    n = 0
    for room in ROOMS:
        for p in sorted(Path(SRC_DIR).glob(f"채권_{room}_{ymd}_*.txt")):
            try:
                txt = p.read_text(encoding="cp949", errors="replace")
            except OSError:
                continue
            for sender, tm, body in split_messages(txt):
                n += 1
                try:
                    b.feed(room, sender, tm, body)
                except Exception:                        # noqa: BLE001
                    pass

    def fold(entries, fills):
        by = {}
        for e in entries:
            by.setdefault(e["code"], []).append(e)
        out = {}
        for code in set(by) | set(fills):
            ent = by.get(code, [])
            fa, fb = uncross_best(ent)
            mid = round((fa["y"] + fb["y"]) / 2, 4) if (fa and fb) else None
            f = fills.get(code) or {}
            # 통안·국민주택은 민평이 엔트리에 실려 온다 (국고는 ref 의 mp 로 충분)
            mpv = next((e["mp"] for e in ent if e.get("mp") is not None), None)
            out[code] = {"a": fa["y"] if fa else None,
                         "b": fb["y"] if fb else None,
                         "mid": mid, "fill": f.get("y"), "mp": mpv,
                         "n": len(ent)}
        return out

    return {"v": PREV_V, "date": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}", "n_msg": n,
            "pulse": b.pulse, "n_dealer": len(b.dealers),
            "ktb": fold(list(b.ktb.values()), b.kfills),
            "msb": fold(list(b.msb.values()), b.mfills),
            "nhb": fold(b._resolve_nhb(), b.nhb_fills)}


def load_prev(ref):
    """캐시가 있으면 읽고, 없으면 접어서 캐시에 쓴다. 실패해도 조용히 넘어간다."""
    ymd = last_log_day()
    if not ymd:
        return None
    cache = PREV_DIR / f"prev_day_{ymd}.json"
    try:
        if cache.exists():
            d = json.loads(cache.read_text(encoding="utf-8"))
            if d.get("v") == PREV_V:
                log(f"[어제] 캐시 {cache.name} · 국고 {len(d.get('ktb', {}))}종")
                return d
            log(f"[어제] 캐시 {cache.name} 가 옛 판(v{d.get('v', 1)}) — 다시 접는다")
    except Exception as e:                               # noqa: BLE001
        log(f"[어제] 캐시 읽기 실패: {type(e).__name__}: {e}")
    t0 = time.time()
    d = prev_summary(ref, ymd)
    try:
        cache.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        log(f"[어제] 캐시 쓰기 실패: {e}")
    log(f"[어제] {d['date']} 접음 {time.time() - t0:.1f}초 · "
        f"국고 {len(d['ktb'])}종 · 통안 {len(d['msb'])}종 · 국주 {len(d['nhb'])}종")
    return d


def start_engine(at=None, seed_prev_day=True):
    """책을 세우고 폴링 함수를 돌려준다. HTTP 서버는 부르는 쪽이 띄운다.

    ★이것이 «엔진의 단 하나의 기동 경로» 다. FastAPI 판(`kbond_api.py`)과 옛
      `http.server` 판이 같은 것을 부른다 — 두 벌로 두면 언젠가 갈라진다.
    반환: (book, poll, ref). poll() 을 주기적으로 부르면 STATE 가 갱신된다.
    """
    ref = {"mp": {}, "date": "없음", "mats": {}, "tenors": {}, "names": {},
           "bench": [], "nextbench": [], "linkers": [], "msb_mst": pd.DataFrame(),
           "mp31": {}, "auction": None}
    for i in range(5):
        try:
            ref = load_mp_latest()
            break
        except Exception as e:                           # noqa: BLE001
            log(f"[민평 로드 실패 {i + 1}/5] {type(e).__name__}: {e}")
            time.sleep(10)
    if not ref["mp"]:
        log("[경고] 민평 없이 기동 — 축약호가 복원 불가, 문면 절대금리만 접는다")
    try:
        ref["mtx"] = load_matrix_latest()
    except Exception as e:                               # noqa: BLE001
        log(f"[매트릭스] {type(e).__name__}: {e}")
        ref["mtx"] = None
    book = Book(ref)
    tail = Tail()

    # 시작 시 오늘치 전체를 한 번 접는다 (아침이 아니라 장중에 켜도 책이 선다)
    FORCE = {"v": False}                 # 어제 책이 늦게 도착하면 한 번 밀어 준다

    def poll():
        changed = False
        for room, chunk in tail.read_new():
            for sender, tm, body in split_messages(chunk):
                changed = True
                try:
                    book.feed(room, sender, tm, body)
                except Exception as e:                   # noqa: BLE001
                    log(f"[feed 오류] {type(e).__name__}: {e} :: {body[:60]}")
        book.sample_mid()
        if changed or STATE["ver"] == 0 or FORCE["v"]:
            FORCE["v"] = False
            snap = book.snapshot()
            raw = json.dumps(snap, ensure_ascii=False).encode("utf-8")
            with STATE["lock"]:
                STATE["book"] = snap
                STATE["raw"] = raw
                STATE["stream"] = book.stream
                STATE["ver"] += 1
                if changed:
                    STATE["last_evt"] = time.time()
            with COND:
                COND.notify_all()

    # ★기동 되감기(라이브·리플레이 공통). 오늘 파일을 방을 가로질러 «시각순» 으로
    #   먹이면서 10초마다 mid 를 표본한다. 한 번에 먹이면 hist 가 한 점만 남아
    #   장중에 재시작했을 때 시세 차트가 통째로 사라진다.
    msgs = []
    for room, chunk in tail.read_new():
        for sender, tm, body in split_messages(chunk):
            msgs.append((tsec(tm) or 0, room, sender, tm, body))
    msgs.sort(key=lambda r: r[0])
    if at is not None:
        msgs = [r for r in msgs if r[0] <= at]
    mark = 0
    for _t, room, sender, tm, body in msgs:
        try:
            book.feed(room, sender, tm, body)
        except Exception as e:                           # noqa: BLE001
            log(f"[feed 오류] {type(e).__name__}: {e} :: {body[:60]}")
        if book.vnow - mark >= 10:
            mark = book.vnow
            book.sample_mid(book.vnow)
    if at is not None:
        book.vnow = at
    log(f"[되감기] {today_str()} · {len(msgs):,}건 · 시계 {book.clock()}s")

    poll()
    log(f"[기동] 오늘 메시지 {book.n_msg:,} · 국고 {len(book.ktb)} · "
        f"크레딧 {len(book.credit)} · 바구니 {len(book.baskets)}")


    if seed_prev_day:
        def _seed():
            try:
                book.prev = load_prev(ref)
                FORCE["v"] = True
            except Exception as e:                       # noqa: BLE001
                log(f"[어제] 실패: {type(e).__name__}: {e}")
        threading.Thread(target=_seed, daemon=True).start()
    return book, poll, ref


def main() -> int:
    global REPLAY, PORT, VIEWER, REPLAY_AT
    argv = sys.argv[1:]
    if "--viewer" in argv:
        VIEWER = Path(argv[argv.index("--viewer") + 1])
    if "--replay" in argv:
        REPLAY = argv[argv.index("--replay") + 1]
    at = None
    if "--at" in argv:                       # 리플레이 시계를 장중 한 시점에 세운다
        h, m, sec = (argv[argv.index("--at") + 1] + ":0:0").split(":")[:3]
        at = int(h) * 3600 + int(m) * 60 + int(sec)
        REPLAY_AT = at
    if "--port" in argv:
        PORT = int(argv[argv.index("--port") + 1])
    # ★v8.1 [OWNER 「최종 감사 뒤 Tailscale 로」] — 바인딩 주소를 인자로. 기본은 로컬뿐.
    #   Tailscale 이면 `--host 100.x.y.z`(테일넷 IP) 또는 `--host 0.0.0.0`.
    global HOST, MASK
    if "--no-mask" in argv:
        MASK = False
        log("[가림] 꺼짐 — 딜러 이름·전화가 그대로 나간다(로컬 확인용)")
    if "--host" in argv:
        HOST = argv[argv.index("--host") + 1]
    book, poll, ref = start_engine(at=at)

    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"[서빙] http://{HOST}:{PORT}/  (파일 폴링 {POLL_S}초 · SSE 푸시"
        f"{' · 딜러 가림' if MASK else ' · 가림 꺼짐'}"
        f"{' · 토큰' if TOKEN else ''})")
    if not TOKEN:
        # ★[OWNER 2026-09-03] 「토큰 빼고 Funnel 유지」 — 위험을 알린 뒤의 결정이다.
        #   남은 문턱은 CORS 하나뿐이고 그건 «브라우저» 만 막는다. curl 로는 주소를
        #   아는 누구나 책 전체를 받는다(딜러는 가려져 있지만 호가·체결·민평은 그대로).
        #   되돌리려면 사용자 환경변수 KBOND_TOKEN 을 넣고 이 태스크를 재기동하면 된다.
        log("[문턱] 토큰 없음 [OWNER 결정] — 인증 없이 연다. Funnel 에 걸려 있으면 "
            "주소를 아는 누구나 받는다.")
    if HOST not in ("127.0.0.1", "localhost"):
        # ★[2026-09-03 감사] 이 책에는 딜러 데스크 이름과 전화번호가 그대로 들어 있고
        #   (스냅샷 안에 전화번호꼴 403개) 서버에는 인증이 없다. 로컬 밖으로 여는 순간
        #   그 주소에 닿는 누구나 전량을 받는다. 이 PC 는 Tailscale Funnel 이 이미
        #   :443·:8443 에서 인터넷에 열려 있다(8100·8200) — 거기에 이 포트를 붙이면
        #   테일넷이 아니라 인터넷 공개가 된다.
        log(f"[경고] 로컬 밖({HOST})에 열렸다 — 인증이 없고 딜러 이름·전화가 그대로 나간다. "
            f"테일넷 전용이면 `tailscale serve`(Funnel 아님)로 붙이고, "
            f"Funnel 에는 붙이지 말 것.")

    try:
        while True:
            time.sleep(POLL_S)
            try:
                poll()
            except Exception as e:                       # noqa: BLE001
                # 일시적 파일 잠금·디코딩 오류가 루프를 죽이면 안 된다.
                log(f"[poll 오류] {type(e).__name__}: {e}")
                time.sleep(2)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
