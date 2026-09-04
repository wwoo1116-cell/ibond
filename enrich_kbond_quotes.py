# -*- coding: utf-8 -*-
"""
축약 호가(QuoteRaw) 를 민평으로 복원해 절대금리(QuoteYield) 를 채운다.

메신저는 앞자리를 떼고 쓴다. '24-13 815-' 의 815 는 3.815 일 수도 4.815 일
수도 있고, '24-4 74사자' 의 74 는 3.740 일 수도 3.474 일 수도 있다.
원문만으로는 복원이 불가능하므로 **그날 그 종목의 민평**을 기준점으로 삼는다.

  1) infomax.ontherun_schedule 의 종목명 '국고02875-4409(24-10)' 에서
     지표코드 -> 표준코드(ISIN) 를 뽑는다.
  2) infomax.국고통_민평 에서 (일자, ISIN) 민평을 가져온다.
  3) 자릿수별 후보를 만들어 **민평에 가장 가까운 값**을 고른다.
        '815'(3자리) -> floor(민평) + 0.815
        '74'(2자리)  -> floor(민평) + 0.74      (경향신문 해설: '50' = 3.50)
                     -> 민평의 소수 첫자리 유지 + 0.074   (예: 3.4|74 = 3.474)
     둘 중 민평과의 거리가 짧은 쪽. 25bp 를 넘으면 복원 실패로 두고 NULL.

또한 '원' 단위 호가를 bp 로 환산한다 [OWNER 자료, 2026-08-27].

  만기 1년 내외 채권은 YTM 이 아니라 **액면 1만원당 단가**로 호가한다.
  전일 민평 단가 대비 +1원/-2원 식이고 최소 단위는 0.25원, 민평 단가의
  소수점 이하는 절사한 뒤 시작한다. 데이터가 이 규칙과 맞는다:
    - '원' 호가 890,486건 중 0.25 배수가 97.63%
    - '원' 호가 종목의 잔존만기 중앙값 0.71년, 1년 이하 77.3% / 2년 이하 99.5%

  단가 1원 = 수정듀레이션 1년당 1bp 이므로  bp = -원 / D_mod  이다.
  254,337건(민평·절대금리·만기가 모두 있는 행)으로 실측한 결과 함의
  듀레이션이 잔존만기와 거의 같았다 — 만기 1년 안쪽은 현금흐름이 사실상
  하나라 D_mod ≈ TTM 이 된다:

    잔존만기      실측 bp/원   함의 D    1/TTM
    0.00~0.25년      5.20      0.19     6.52
    0.25~0.50년      2.48      0.40     2.61
    0.50~0.75년      1.57      0.64     1.58
    0.75~1.00년      1.12      0.89     1.12
    1.00~1.50년      0.87      1.15     0.84
    1.50~2.00년      0.63      1.58     0.61
    2.00~3.00년      0.42      2.35     0.42

  그래서 환산은 가정이 아니라 이 실측표를 보간해서 쓴다.
  'bp/빕' 표기는 금리 단위라 부호 그대로 옮긴다.

추가되는 컬럼
  MPYieldDB        그날 그 종목의 민평(DB)
  QuoteYield       복원된 절대금리(%)
  QuoteMethod      복원에 쓴 후보 유형(handle3 / handle2 / decimal2)
  QuoteVsMP_bp     QuoteYield - MPYieldDB, bp
  TTM_years        메시지의 만기일 - 발언일 (년)
  MPPriceFrac      '끝54' '끝전.17' -> 민평 단가의 소수부(절사 규칙에 필요)
  SpreadBpEst      스프레드를 bp 로 통일한 값(원은 듀레이션 환산, bp는 그대로)
  CodeCollision    본문 민평과 DB 민평이 25bp 넘게 어긋난 행. 섹터 판정이
                   원천에서 막고 있는지 재는 계기판이다(값을 버리지는 않는다).
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from parse_kbond_logs import (RE_ABS_YIELD, RE_ABS_YIELD2, RE_COUPON_MASK,  # noqa
                              RE_LIST_FRAC, RE_MP_YIELD, RE_MSB_ITEM,
                              split_broker)
from sqlalchemy import create_engine, text

BASE = Path(r"C:\Users\infomax\Projects\data\kbond")
PARQUET = BASE / "kbond_structured_data.parquet"
OUT_PARQUET = BASE / "kbond_structured_data.parquet"
OUT_CSV = BASE / "kbond_structured_data.csv"
MAX_DIFF = 0.25          # 민평에서 25bp 넘게 떨어지면 복원 실패로 본다
CHUNK = 500_000

# 실측 bp/원 (잔존만기 구간 중앙값). 독스트링의 표와 같다.
TTM_GRID = np.array([0.125, 0.375, 0.625, 0.875, 1.25, 1.75, 2.50])
BP_PER_WON = np.array([5.20, 2.48, 1.57, 1.12, 0.87, 0.63, 0.42])

# 만기일 25.4.18 / 24.8.28  (본문에서 뽑아 둔 Maturity 컬럼 형식)
# '민평팔자' '민 팔자' '민평매도' — 민평 수준에 거래한다고 문면이 말한 행.
# 전수조사: ~198K 행. 승격 오차 중앙 +0.6bp, 쿠폰 필터 후 95.2%가 5bp 이내.
# 확정 호가와 반드시 구분해야 하므로 QuoteMethod='at_mp' 로 따로 표시한다.
RE_AT_MP = re.compile(r'민\s*(?:평)?\s*(?:에서)?\s*(?:팔자|사자|매도|매수|거래|체결)'
                      r'|민평\s*(?:수준|레벨)')
# 쿠폰/지수 문맥 — 승격 대상에서 제외한다(AbsYield 슬롯 오염 방지).
RE_COUPON_CTX = re.compile(r'표면|쿠폰|이표|표리|쿠\s?\.?\d|저쿠'
                           r'|FRN|CD\s*9?1?\s*\+|CMS|IRS', re.IGNORECASE)
# ★2026-09-01 감사: '끝전0.4' 형에서 선행 0 을 먹고 '4' 가 아니라 '0' 을 잡아
# 53,595행이 MPPriceFrac=0.0 이 됐다. 범위검사를 통과하는 틀린 값이라 더 위험했다.
# 두 갈래로 나눈다 — 소수점형('끝전0.4' '끝.45')과 정수형('끝54' '끝전 9').
RE_MP_FRAC = re.compile(r'끝\s*(?:전)?\s*0?\.\s*(\d{1,2})'
                        r'|끝\s*(?:전)?\s*(\d{1,2})(?!\s*[.\d])')

DERIVED = ["MPYieldDB", "QuoteYield", "QuoteMethod", "QuoteVsMP_bp",
           "MPBase", "QuoteBlockReason", "MSBCode", "MSBSource",
           # 2026-09-02 [OWNER]: 국딱 = 그날 입찰된 국고채 (§10)
           "AuctionCode", "AuctionTenor", "QuoteConfidence",
           "TTM_years", "MPPriceFrac", "SpreadBpEst", "CodeCollision"]


def maturity_to_ts(s):
    """'25.4.18' -> Timestamp. 실패하면 NaT."""
    try:
        y, m, d = s.split(".")
        return pd.Timestamp(2000 + int(y), int(m), int(d))
    except Exception:                                    # noqa: BLE001
        return pd.NaT


def won_to_bp(spread_won, ttm):
    """단가 원 -> bp. 실측표를 보간하고, 표 밖은 1/TTM(D_mod≈TTM)으로 잇는다."""
    r = np.interp(ttm, TTM_GRID, BP_PER_WON, left=np.nan, right=np.nan)
    out_of_range = np.isnan(r)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(out_of_range, np.where(ttm > 0, 1.0 / ttm, np.nan), r)
    return -spread_won * r


def engine(db="infomax"):
    need = ["BW_MYSQL_USER", "BW_MYSQL_PASSWORD", "BW_MYSQL_HOST", "BW_MYSQL_PORT"]
    miss = [k for k in need if not os.environ.get(k)]
    if miss:
        sys.exit(f"[FATAL] 환경변수 미설정: {miss}")
    return create_engine(
        f"mysql+pymysql://{os.environ['BW_MYSQL_USER']}:{os.environ['BW_MYSQL_PASSWORD']}"
        f"@{os.environ['BW_MYSQL_HOST']}:{os.environ['BW_MYSQL_PORT']}/{db}?charset=utf8mb4",
        pool_pre_ping=True)


def norm_code(s: pd.Series) -> pd.Series:
    """'23-01' 과 '23-1' 은 같은 종목이다. 제로패딩을 없앤다."""
    return s.str.replace(r'^(\d{2})-0*(\d+)$', r'\1-\2', regex=True)


def load_mp(dates):
    """지표코드 -> ISIN 매핑 + 해당 기간 민평.

    ★2026-09-02 라이브 검증에서 잡힌 구멍: ontherun_schedule 은 지표지정 이력이라
    마지막 지정일(실측 2026-06-10) 뒤에 발행된 종목(26-7·26-9…)의 ISIN 이 없다.
    그날 26-7 이 최활발 종목이었는데 민평이 안 붙어 통째로 빠지고 있었다.
    `국채_발행정보` 의 종목명이 'YY-N' 꼴이라 거기서도 얻어 합집합으로 쓴다.
    """
    with engine().connect() as c:
        otr = pd.read_sql(text("SELECT DISTINCT 종목명, 표준코드 FROM ontherun_schedule"), c)
        iss = pd.read_sql(text(
            "SELECT 표준코드, 종목명 FROM `국채_발행정보` "
            "WHERE 종목명 REGEXP '^[0-9]{1,2}-[0-9]{1,2}$'"), c)
        otr["BondCode"] = otr["종목명"].str.extract(r'\((\d{2}-\d{1,2})\)')
        otr = otr.dropna(subset=["BondCode"])
        iss = iss.rename(columns={"종목명": "BondCode"})
        otr = pd.concat([otr[["BondCode", "표준코드"]], iss[["BondCode", "표준코드"]]])
        otr["BondCode"] = norm_code(otr["BondCode"])
        otr = otr.drop_duplicates("BondCode", keep="last")
        isins = tuple(otr["표준코드"].unique())
        print(f"  지표코드 -> ISIN 매핑 {len(otr):,}종 (ontherun + 국채_발행정보 합집합)")

        mp = pd.read_sql(
            text("SELECT 일자, 종목코드, 민평 FROM `국고통_민평` "
                 "WHERE 일자 BETWEEN :a AND :b AND 종목코드 IN :isins"),
            c, params={"a": str(dates.min()), "b": str(dates.max()), "isins": isins})
    print(f"  민평 {len(mp):,}행 ({mp['일자'].min().date()} ~ {mp['일자'].max().date()})")
    mp = mp.merge(otr[["BondCode", "표준코드"]], left_on="종목코드", right_on="표준코드")
    mp = mp.rename(columns={"일자": "Date", "민평": "MPYieldDB"})
    return mp[["Date", "BondCode", "MPYieldDB"]].drop_duplicates(["Date", "BondCode"])


# 통안 은어 -> (만기구분, 발행순위). 2026-09-01 판별 검정으로 확정.
#   '구'=舊(한 단계 이전) · '삼'=3년물 · 딱=당일 발행분
#   적중률(가설 대 인접): 통당 98.6/85.2 · 구통 98.6/83.8 · 구구통 99.1/86.7
#                        삼통 98.4/80.0 · 구삼통 98.3/88.3 · 구구삼통 96.6/79.3
MSB_SLANG = {
    "구구삼통": ("3.0Y", 2), "구삼통": ("3.0Y", 1), "삼딱": ("3.0Y", 0),
    "삼통당": ("3.0Y", 0), "삼통": ("3.0Y", 0),
    "구구통": ("2.0Y", 2), "구통당": ("2.0Y", 1), "구통": ("2.0Y", 1),
    "통딱": ("2.0Y", 0), "통당": ("2.0Y", 0),
    # ★'N년통' 은 발행만기가 아니라 **잔존만기** 지칭이다(2026-09-01 KIS 축 실측).
    #   2년물이 분기 발행이라 사다리 한 칸이 3개월 —
    #   통당 r0=잔존 2.0년 · 구통 r1=1.75 · 구구통 r2=1.5 · r4=1.0
    #   KIS 대조: 1.5년통 = 2.0Y r2 (중앙 +0.00bp · 1bp 이내 98.2%, 구구통과 같은 종목)
    #             1년통   = 2.0Y r4 (중앙 +0.00bp · 1bp 이내 81.8%)
    #   ⚠ 1년물(1Y) 신규가 아니다 — 1Y r1 은 -3.3bp 로 어긋난다.
    "1.5년통": ("2.0Y", 2), "1.5년 통": ("2.0Y", 2),
    "1년통": ("2.0Y", 4), "1년 통": ("2.0Y", 4),
}
# 긴 낱말이 먼저 걸려야 한다(구구삼통이 삼통보다, 구구통이 구통보다).
MSB_ORDER = sorted(MSB_SLANG, key=len, reverse=True)


# ★'국딱' = 그날 입찰된 국고채. 만기가 아니라 상태다(§10, 2026-09-02 확정).
# 앞 경계만 건다 — 뒤 경계를 넣으면 '국딱팔고' 가 잘린다.
RE_GUKTTAK = re.compile(r'(?<![가-힣])국딱')


def load_auction(dates):
    """입찰일 -> (그날 낙찰 종목 표준코드, 그 종목 민평, 만기).

    국고채는 입찰일마다 만기가 하나만 열린다(246일 전부 nunique=1 실측).
    그래서 날짜 하나가 종목 하나를 정한다. 검증축은 `낙찰금리` 다 —
    국딱 호가의 소수부가 낙찰금리 소수부에 붙는 것을 이미 확인했다
    (2Y R=0.981 · 3Y 0.992 · 5Y 0.998 · 10Y 0.989 · 20Y 0.984 · 30Y 0.986).
    """
    d0, d1 = pd.to_datetime(dates).min(), pd.to_datetime(dates).max()
    with engine().connect() as c:
        au = pd.read_sql(text(
            "SELECT 입찰일, 표준코드, 만기, 낙찰금리 FROM `국채_입찰` "
            "WHERE 구분='경쟁' AND 입찰일 BETWEEN :a AND :b"),
            c, params={"a": str(d0.date()), "b": str(d1.date())})
        mp = pd.read_sql(text(
            "SELECT 일자, 종목코드, 민평 FROM `국고통_민평` "
            "WHERE 종목코드 LIKE 'KR10%' AND 일자 BETWEEN :a AND :b"),
            c, params={"a": str(d0.date()), "b": str(d1.date())})
    au["입찰일"] = pd.to_datetime(au["입찰일"]).dt.normalize()
    au = au.dropna(subset=["표준코드"]).drop_duplicates("입찰일", keep="first")
    mp["일자"] = pd.to_datetime(mp["일자"])
    mp = mp[mp["민평"].between(0.3, 9)]
    mpmap = {(d, c_): v for d, c_, v in zip(mp["일자"], mp["종목코드"], mp["민평"])}
    code = dict(zip(au["입찰일"], au["표준코드"]))
    tenor = dict(zip(au["입찰일"], pd.to_numeric(au["만기"], errors="coerce")))
    # 입찰 당일에는 신규 종목의 민평이 아직 없을 수 있다. 없으면 낙찰금리로 대신한다
    # (그날 그 종목의 시장 수준을 말하는 가장 가까운 관측치다).
    won = dict(zip(au["입찰일"], au["낙찰금리"]))
    mpv = {d: mpmap.get((d, code[d]), won.get(d)) for d in code}
    print(f"      국채 입찰 {len(au):,}일 · 민평/낙찰금리 확보 "
          f"{sum(v is not None and pd.notna(v) for v in mpv.values()):,}일")
    return {"code": code, "mp": mpv, "tenor": tenor}


def load_msb(dates):
    """통안 마스터 + 민평. 국고와 달리 ontherun_schedule 에 없어서 따로 읽는다."""
    with engine().connect() as c:
        mst = pd.read_sql(text("SELECT 표준코드, 종목명, 발행일, 만기일, 인포맥스소분류 "
                               "FROM `통안채_발행정보`"), c)
        mp = pd.read_sql(
            text("SELECT 일자, 종목코드, 민평 FROM `국고통_민평` "
                 "WHERE 종목코드 LIKE 'KR31%' AND 일자 BETWEEN :a AND :b"),
            c, params={"a": str(dates.min()), "b": str(dates.max())})
    mst["발행일"] = pd.to_datetime(mst["발행일"])
    mst["만기일"] = pd.to_datetime(mst["만기일"])
    mp["일자"] = pd.to_datetime(mp["일자"])
    mp = mp[mp["민평"].between(0.3, 9)]
    print(f"  통안 마스터 {len(mst):,}종 · 민평 {len(mp):,}행")
    return mst, mp


def msb_join(df, mst, mp):
    """통안 행에 민평을 붙인다. 두 경로 — 은어 사다리, 종목 직접 표기."""
    mpmap = {(r.일자, r.종목코드): r.민평 for r in mp.itertuples()}
    # 날짜 x 만기구분 -> 발행일 내림차순 표준코드
    ladder = {}
    for d in pd.to_datetime(sorted(mp["일자"].unique())):
        alive = mst[(mst["발행일"] <= d) & (mst["만기일"] > d)]
        for k, g in alive.groupby("인포맥스소분류"):
            ladder[(d, k)] = list(g.sort_values("발행일", ascending=False)["표준코드"])
    # 종목명 -> 표준코드 (두 갈래: tenor 코드형 / 만기일형)
    by_name = dict(zip(mst["종목명"].str.replace(r"\s", "", regex=True), mst["표준코드"]))
    by_matd = {}
    for r in mst.itertuples():
        k = f"{r.만기일:%y.%m.%d}통"
        by_matd.setdefault(k, r.표준코드)

    core = df["Message"].astype(str).map(lambda m: split_broker(m)[1])
    isin = pd.Series(pd.NA, index=df.index, dtype="object")
    src = pd.Series(pd.NA, index=df.index, dtype="object")

    # (1) 종목 직접 표기가 우선한다 — 은어보다 구체적이다.
    it = core.str.extract(RE_MSB_ITEM)
    ok = it[0].notna()
    for i in df.index[ok]:
        y, m_, d_ = it.loc[i, 0], int(it.loc[i, 1]), int(it.loc[i, 2])
        code = by_name.get(f"{y}.{m_:02d}.{d_:02d}통") or by_matd.get(f"{y}.{m_:02d}.{d_:02d}통")
        if code:
            isin.loc[i], src.loc[i] = code, "item"

    # (2) 은어 사다리
    need = isin.isna()
    for w in MSB_ORDER:
        kind, rank = MSB_SLANG[w]
        hit = need & core.str.contains(w, regex=False, na=False)
        for i in df.index[hit]:
            lad = ladder.get((pd.Timestamp(df.at[i, "Date"]), kind))
            if lad and rank < len(lad):
                isin.loc[i], src.loc[i] = lad[rank], "slang"
        need = isin.isna()

    mpv = pd.Series([mpmap.get((pd.Timestamp(d), c_)) if c_ is not pd.NA else None
                     for d, c_ in zip(df["Date"], isin)], index=df.index, dtype="float64")
    return isin, src, mpv


def restore(quote_raw: pd.Series, mp: pd.Series):
    """축약 호가 + 민평 -> 절대금리. 민평에 가장 가까운 후보를 고른다."""
    # ★2026-09-01 감사: '405.41+' 같은 양방/세트 토큰을 RE_QUOTE_RAW 가 한 덩이로
    # 잡는데 점을 지우면 4~6자리가 되어 어느 후보에도 안 걸리고 22,265행이 조용히
    # NULL 이 됐다. 점을 다리 구분자로 보고 **뒤 다리**를 쓴다(그 행의 호가는
    # 보통 뒤쪽이다 — 앞은 짝의 반대편이다). 두 다리 다 필요하면 kbond_legs 몫이다.
    _raw = quote_raw.astype(str)
    _two = _raw.str.match(r'^\d{2,3}\.\d{2,3}$')
    _raw = _raw.where(~_two, _raw.str.split(".").str[-1])
    digits = _raw.str.replace(".", "", regex=False)
    n = digits.str.len()
    val = pd.to_numeric(digits, errors="coerce")
    floor = np.floor(mp)

    # ★2026-09-01 감사 두 건을 여기서 함께 닫는다.
    #  (1) decimal2(3.4|74 -> 3.474)는 **존재하지 않는 관행**이었다. 150,110행이
    #      틀린 값을 실었다. 독립축 둘로 확인 — 세트 표기 'NNN/NN' 에서 2자리 짝을
    #      handle2 로 읽으면 앵커와 정확히 0.5bp 인 비율 99.6%인데 decimal2 로
    #      읽으면 0.78% 다. 또 3자리 토큰 끝자리는 99.82%가 '5'(0.5bp 격자)인데
    #      decimal2 산출값만 셋째 소수가 균등분포로 격자를 벗어난다.
    #  (2) 정수부 후보가 floor 하나뿐이라 핸들 경계에서 handle 후보가 100bp 튕겨
    #      나가고 decimal2 가 25bp 가드를 통과해 ~10bp 틀린 값을 낚아챘다(10,080행).
    #      floor±1 을 넣으면 그 자리가 정상 복원되고, 25bp 가드에 버려졌던
    #      3자리 5,735행도 살아난다(±1 후보는 100bp 떨어져 동시 채택 불가).
    cands, names = [], []
    for shift in (0.0, 1.0, -1.0):
        base = floor + shift
        cands.append(np.where(n == 3, base + val / 1000.0, np.nan))
        names.append("handle3")
        cands.append(np.where(n == 2, base + val / 100.0, np.nan))
        names.append("handle2")

    C = np.vstack(cands)                     # (후보, 행)
    D = np.abs(C - mp.to_numpy()[None, :])
    D = np.where(np.isnan(C), np.inf, D)
    best = np.argmin(D, axis=0)
    bestd = D[best, np.arange(D.shape[1])]
    out = C[best, np.arange(C.shape[1])]
    method = np.array(names, dtype=object)[best]
    bad = (~np.isfinite(bestd)) | (bestd > MAX_DIFF)
    out = np.where(bad, np.nan, out)
    method = np.where(bad, None, method)
    return out, method


def main():
    t0 = time.time()
    print(f"[1/4] 적재 {PARQUET}")
    df = pd.read_parquet(PARQUET)
    print(f"      {len(df):,}행")
    # 여러 번 돌려도 같은 결과가 나오도록 파생 컬럼을 먼저 지운다
    df = df.drop(columns=[c for c in DERIVED if c in df.columns])

    print("[2/4] 민평 조회")
    mp = load_mp(df["Date"].dt.date)

    print("[3/4] 복원")
    # 국고 지표물로 판정된 행에만 붙인다. 국민주택 1종('국주 23-03') 처럼
    # 같은 표기를 쓰는 다른 물건에 국고 민평을 붙이면 안 된다.
    df["_code"] = norm_code(df["BondCode"].fillna("")).where(df["Sector"] == "국고", "")
    df = df.merge(mp, how="left", left_on=["Date", "_code"], right_on=["Date", "BondCode"],
                  suffixes=("", "_m"))
    df = df.drop(columns=[c for c in ("BondCode_m", "_code") if c in df.columns])

    # --- 2차 안전망
    # 1차 방어는 파서다. 섹터를 먼저 판정하고 국고일 때만 YY-N 을 지표물 코드로
    # 읽으므로 MBS/국민주택/도시철도채/발행체회차는 원천에서 걸러진다.
    # 여기 남는 것은 한 메시지가 여러 종목을 동시에 말하는 경우 같은 잔여다.
    # 본문에 민평이 적힌 행에서만 작동하므로 이것만으로는 부족하다 — 그래서
    # 1차가 파서여야 했다. 잡히는 것만이라도 버린다.
    both_mp = df["MPYield"].notna() & df["MPYieldDB"].notna()
    collide = both_mp & ((df["MPYield"] - df["MPYieldDB"]).abs() > 0.25)
    df["CodeCollision"] = collide
    df.loc[collide, "MPYieldDB"] = np.nan
    print(f"      2차 안전망: 잔여 충돌 {int(collide.sum()):,}행 폐기 "
          f"(대조 가능 {int(both_mp.sum()):,}행 중 "
          f"{collide.sum() / max(both_mp.sum(), 1) * 100:.1f}%)")

    # ★2026-09-01: 통안은 ontherun_schedule 에 없어 민평이 한 행도 안 붙었다
    # (Sector='통안' 61.5만행 전량). 은어 사다리와 종목 표기로 붙인다.
    _msb = df["Sector"].eq("통안")
    if _msb.any():
        mst_m, mp_m = load_msb(df.loc[_msb, "Date"])
        _isin, _src, _mpv = msb_join(df.loc[_msb], mst_m, mp_m)
        df.loc[_msb, "MSBCode"] = _isin
        df.loc[_msb, "MSBSource"] = _src
        df.loc[_msb, "MPYieldDB"] = df.loc[_msb, "MPYieldDB"].fillna(_mpv)
        print(f"      통안 민평 조인 {int(_mpv.notna().sum()):,}행 "
              f"(종목표기 {int((_src == 'item').sum()):,} · "
              f"은어 {int((_src == 'slang').sum()):,})")

    # ★2026-09-02 [OWNER 「붙이세요」]: '국딱' = 그날 입찰된 국고채(§10).
    # 만기가 아니라 상태라서 고정 사다리로는 못 붙이고, 그날 입찰 종목으로 붙는다.
    _gd = df["Message"].astype(str).str.contains(RE_GUKTTAK, na=False)
    if _gd.any():
        au = load_auction(df.loc[_gd, "Date"])
        # ⚠ 이 행들 중 일부는 이미 BondCode 를 갖고 있는데 그건 국딱이 아니라
        #   «짝 다리» 코드다('국딱 팔고 24-8 사자'). MPYieldDB 를 덮으면
        #   짝의 민평 자리에 국딱 민평이 들어간다 -> 코드가 없는 행에만 붙인다.
        _safe = _gd & df["BondCode"].isna() & df["MPYieldDB"].isna()
        key = df.loc[_safe, "Date"].dt.normalize()
        df.loc[_safe, "AuctionCode"] = key.map(au["code"])
        df.loc[_safe, "MPYieldDB"] = key.map(au["mp"])
        df.loc[_safe, "AuctionTenor"] = key.map(au["tenor"])
        _n = int(key.map(au["mp"]).notna().sum())
        print(f"      국딱 입찰 조인 {_n:,}행 "
              f"(대상 {int(_gd.sum()):,} · 짝코드 보유라 제외 "
              f"{int((_gd & ~_safe).sum()):,})")

    m = df["QuoteRaw"].notna() & df["MPYieldDB"].notna()
    df["QuoteYield"] = np.nan
    df["QuoteMethod"] = None
    y, meth = restore(df.loc[m, "QuoteRaw"], df.loc[m, "MPYieldDB"])
    df.loc[m, "QuoteYield"] = y
    df.loc[m, "QuoteMethod"] = meth

    df["QuoteVsMP_bp"] = (df["QuoteYield"] - df["MPYieldDB"]) * 100

    # --- 잔존만기 / 민평 단가 끝전 / 스프레드 bp 통일
    mat = df["Maturity"].dropna().drop_duplicates()
    lut = {s: maturity_to_ts(s) for s in mat}
    df["TTM_years"] = ((df["Maturity"].map(lut) - df["Date"]).dt.days / 365.25)
    df.loc[(df["TTM_years"] <= 0) | (df["TTM_years"] > 40), "TTM_years"] = np.nan

    _f = df["Message"].str.extract(RE_MP_FRAC)
    frac = _f[0].fillna(_f[1])
    # '(민 2.883%, 0.76원)' 목록형의 뒤 숫자는 끝전이다(2026-09-01 실측: 평균 0.505,
    # 100%가 1 미만, 0.25 배수 2.9%). 호가로 오인하던 것을 여기로 회수한다.
    frac2 = df["Message"].str.extract(RE_LIST_FRAC, expand=False)
    df["MPPriceFrac"] = pd.to_numeric(("0." + frac).where(frac.notna()), errors="coerce")
    alt = pd.to_numeric(frac2, errors="coerce")
    alt = alt.where(alt.lt(1))
    df["MPPriceFrac"] = df["MPPriceFrac"].fillna(alt)
    # T7: frac 이 NaN 인 행에 "0." 를 붙이면 0.0 으로 파싱된다. 결측은 결측으로 둔다.

    df["SpreadBpEst"] = np.nan
    is_bp = df["SpreadUnit"] == "bp"
    df.loc[is_bp, "SpreadBpEst"] = df.loc[is_bp, "SpreadValue"]        # 금리 단위, 부호 그대로
    # ★2026-09-01 감사: 원 호가는 «전일 민평 단가를 절사한 정수»에서 출발한다
    # [OWNER 자료]. 그 절사분(끝전)을 빼지 않아 QuoteYield 772,236행 전량이
    # 계통적으로 낮았다. 실측 오프셋 중앙 0.434원이고 잔존만기 8구간에서 평평했다
    # (매수/매도·부호 무관 → 듀레이션이 아니라 절사가 원인).
    # 끝전이 안 적힌 행은 균등분포의 기대값 0.5 를 쓴다.
    is_won = (df["SpreadUnit"] == "원") & df["TTM_years"].notna()
    _frac = df["MPPriceFrac"].fillna(0.5)
    df.loc[is_won, "SpreadBpEst"] = won_to_bp(
        (df.loc[is_won, "SpreadValue"] - _frac[is_won]).to_numpy(),
        df.loc[is_won, "TTM_years"].to_numpy())

    # 2026-09-01: 축약호가가 없어도 «민평 + 원 스프레드» 면 금리가 나온다.
    # 841,947행이 이 자리에서 비어 있었다. `won_to_bp` 가 이미 `-spread_won * r` 로
    # 부호를 뒤집어 놓았으므로 SpreadBpEst 는 금리 공간이고 그대로 더하면 된다
    # (기준선 실측: 부호 있는 '+n원' 은 금리 -1.7bp, '-n원' 은 +2.6bp, n=312,006).
    # **bp 표기 쪽은 손대지 않는다** — M2 가 부호 신뢰도 55.3% 로 표시한 자리다.
    mp_any = df["MPYield"].fillna(df["MPYieldDB"])
    m2 = (df["QuoteYield"].isna() & mp_any.notna()
          & df["SpreadBpEst"].notna() & df["SpreadUnit"].eq("원"))
    df.loc[m2, "QuoteYield"] = mp_any[m2] + df.loc[m2, "SpreadBpEst"] / 100.0
    df.loc[m2, "QuoteMethod"] = "spread_won"
    print(f"      «민평 + 원 스프레드» 로 추가 확정 {int(m2.sum()):,}행")

    # ---- 전수조사 승격 3종 (2026-09-01) ----
    # ★2026-09-01 감사: 원문 Message 에 걸어 '(메리츠 CMS 6454-4035)' 같은
    # 데스크 이름의 'CMS' 가 쿠폰 문맥으로 잡혀 12,312행이 근거 없이 탈락했다.
    # 파서와 같은 core(브로커 태그 제거본)에 건다.
    _core = df["Message"].astype(str).map(lambda m: split_broker(m)[1])
    coupon = _core.str.contains(RE_COUPON_CTX, regex=True, na=False)
    at_mp_ctx = _core

    # (가) 문면 민평 + bp 스프레드. enrich 가 MPYieldDB 만 쓰고 문면 MPYield 를
    #     안 써서 ~56K 가 비어 있었다. 검증: 자매 조합에서 |민평+bp − 명시금리|
    #     <=1bp 가 89.5%(반대부호 규칙은 1.0%) — 부호 모호성 없음.
    #     swap/swap_unsigned 는 교체 스프레드라 민평 대비가 아니므로 제외.
    # SpreadSource=='sign' 만 받는다 — swap/swap_unsigned 는 종목간 스프레드라
    # 민평 대비가 아니다(파서가 격리한다). FRN 리셋식도 ~coupon 으로 뺀다.
    m4 = (df["QuoteYield"].isna() & mp_any.notna() & df["SpreadBpEst"].notna()
          & df["SpreadUnit"].eq("bp") & df["SpreadSource"].eq("sign") & ~coupon)
    df.loc[m4, "QuoteYield"] = mp_any[m4] + df.loc[m4, "SpreadBpEst"] / 100.0
    df.loc[m4, "QuoteMethod"] = "mp_plus_bp"
    print(f"      «문면민평 + 부호 bp» 로 추가 확정 {int(m4.sum()):,}행")

    # (나) 문면 절대금리 승격. 쿠폰 오염을 '쿠' 축약까지 걸러야 한다
    #     (전수조사: >100bp 이탈이 9.0% -> 0.8% 로 감소).
    m5 = df["QuoteYield"].isna() & df["AbsYield"].notna() & ~coupon
    df.loc[m5, "QuoteYield"] = df.loc[m5, "AbsYield"]
    # ★신뢰도가 셋이 다르다(2026-09-01 감사). 뭉치면 계기판에 위험이 안 보인다.
    #   _pct   : '3.708%' 명시 — 25bp 초과 이탈 5.8%
    #   _tilde : '~3.581'  — 0.5%
    #   _bare  : 마커 없는 맨몸 — 30.6%. 하류는 이걸 걸러야 한다.
    _masked = _core.map(lambda c: RE_COUPON_MASK.sub(" ", RE_MP_YIELD.sub(" ", str(c))))
    _has_pct = _masked.str.contains(RE_ABS_YIELD, regex=True, na=False)
    _has_tld = _masked.str.contains(RE_ABS_YIELD2, regex=True, na=False)
    df.loc[m5, "QuoteMethod"] = np.where(
        _has_pct[m5], "stated_abs_pct",
        np.where(_has_tld[m5], "stated_abs_tilde", "stated_abs_bare"))
    print(f"      «문면 절대금리» 로 추가 확정 {int(m5.sum()):,}행")

    # (다) 민평 명시 체결('민평팔자'). 호가 수준이 곧 민평이라고 문면이 말한다.
    #     확정 호가가 아니라 '민평에 거래' 라는 약식 표기이므로 method 로 갈라 둔다.
    at_mp = at_mp_ctx.str.contains(RE_AT_MP, regex=True, na=False)
    # ★2026-09-01 감사: at_mp 가 먼저 돌아 '언더2 팔자 / 민 사자' 같은 양방
    # 메시지에서 SELL 행에 BID(민평 플랫) 레벨을 실었다(1,492행).
    # 스프레드가 파싱된 행은 over_under/spread_won 이 가져가게 넘긴다.
    # AXE 는 «파서가 값을 못 본 행» 이라는 계약이다. 파서가 민평 명시를 값으로
    # 세게 됐으므로 여기 남은 AXE 에는 승격하지 않는다(D9 계약 유지).
    m6 = (df["QuoteYield"].isna() & mp_any.notna() & at_mp & ~coupon
          & df["SpreadSource"].isna() & df["MsgType"].ne("AXE"))
    df.loc[m6, "QuoteYield"] = mp_any[m6]
    df.loc[m6, "QuoteMethod"] = "at_mp"
    print(f"      «민평 명시 거래» 로 추가 확정 {int(m6.sum()):,}행")

    # 오버/언더 표기는 부호가 실측으로 확인된다(오버 금리상승 98.1%, 언더 하락 96.4%).
    # M9 닫힘: 한때 «+2bp» 식 기호 표기(SpreadSource='sign')는 M2 가 부호 신뢰도를
    # 55.3% 로 표시해 둔 자리라 올리지 않았는데, 전수조사로 M2 가 99.94% 로 닫혔다.
    # 지금은 위 (가) m4 가 sign 도 올린다. 이 블록은 overunder 몫만 맡는다.
    m3 = (df["QuoteYield"].isna() & mp_any.notna() & df["SpreadBpEst"].notna()
          & df["SpreadUnit"].eq("bp") & df["SpreadSource"].eq("overunder"))
    df.loc[m3, "QuoteYield"] = mp_any[m3] + df.loc[m3, "SpreadBpEst"] / 100.0
    df.loc[m3, "QuoteMethod"] = "over_under"
    print(f"      «민평 + 오버/언더 bp» 로 추가 확정 {int(m3.sum()):,}행")

    # ★2026-09-01 감사: DB 민평 기준으로만 계산해 파생 경로에서 사실상 전멸했다
    # (spread_won 의 0.16%, over_under 의 0.61%만 값이 있었다). 승격에 실제로
    # 쓴 민평(mp_any)을 기준으로 재고, 어느 민평을 썼는지 MPBase 로 남긴다.
    df["MPBase"] = mp_any
    df["QuoteVsMP_bp"] = (df["QuoteYield"] - df["MPBase"]) * 100

    # ★2026-09-01 감사: 호가가 «없는» 행과 «있는데 못 푼» 행이 구분되지 않아
    # 하류가 116,508행을 호가 없음으로 오해할 수 있었다. 사유를 남긴다.
    _has_quote = df[["QuoteRaw", "SpreadValue", "SpreadWonAbs", "AbsYield"]].notna().any(axis=1)
    _blocked = df["QuoteYield"].isna() & _has_quote
    df["QuoteBlockReason"] = None
    df.loc[_blocked & df["MPBase"].isna(), "QuoteBlockReason"] = "no_mp"
    df.loc[_blocked & df["MPBase"].notna() & df["SpreadUnit"].eq("원")
           & df["TTM_years"].isna(), "QuoteBlockReason"] = "no_ttm"
    df.loc[_blocked & df["QuoteBlockReason"].isna(), "QuoteBlockReason"] = "unresolved"
    print(f"      미확정 사유: {df.QuoteBlockReason.value_counts().to_dict()}")

    # ★2026-09-02 [OWNER 승인]: QuoteMethod 신뢰등급.
    # 방식마다 레벨을 얼마나 믿을 수 있는지가 다른데 지금은 뭉쳐 있어서
    # 하류가 «맨몸 숫자» 와 «딜러가 적은 소수부» 를 같은 값으로 쓴다.
    #
    # ⚠ 등급을 «민평 대비 5bp 이내 비율» 로 매기면 안 된다. `at_mp` 는
    #   QuoteYield ≡ 민평이라 그 지표가 **항등식**이고 100% 가 나온다.
    #   복원 계열(handle2/3)도 «민평에 가장 가까운 후보» 를 고르므로 그 지표가
    #   부분적으로 자기참조다. 그래서 등급은 **무엇을 근거로 값을 정했는가**로
    #   매긴다 — 문면이 말한 것인가, 우리가 모형으로 채운 것인가.
    CONF = {
        # 딜러가 소수부를 직접 적었고 정수부만 민평에서 물려받는다.
        "handle3": "high", "handle2": "high",
        # '~3.581' 처럼 마커를 달고 절대금리를 적었다(25bp 초과 이탈 0.5%).
        "stated_abs_tilde": "high",
        # '3.708%' 명시. 이탈 5.8%.
        "stated_abs_pct": "med",
        # 방향이 실측된 한글 부호(오버 98.1% / 언더 96.4%). 크기는 문면 그대로.
        "over_under": "med",
        # 기호 bp. M2 부호 규약 clean 99.94% 위에 선다.
        "mp_plus_bp": "med",
        # 원->bp 는 «환산 모형»이다(듀레이션 보간 + 민평단가 절사 보정).
        # 문면 값이 아니라 우리가 계산한 값이므로 한 단계 낮춘다.
        "spread_won": "med",
        # ★항등식. QuoteYield = 민평 그대로다. «민평에 거래한다» 는 문면을
        #   믿은 것이지 호가 수준을 관측한 것이 아니다. 민평 대비 지표로는
        #   영원히 검증되지 않으므로 따로 표시한다.
        "at_mp": "identity",
        # 마커 없는 맨몸 숫자. 25bp 초과 이탈 30.6% — 하류는 걸러야 한다.
        "stated_abs_bare": "low",
    }
    df["QuoteConfidence"] = df["QuoteMethod"].map(CONF)
    _unk = df["QuoteMethod"].notna() & df["QuoteConfidence"].isna()
    if _unk.any():
        # 새 방식이 생겼는데 등급표에 안 넣은 것. 조용히 넘어가면 안 된다.
        print(f"      [경고] 등급 미지정 QuoteMethod {int(_unk.sum()):,}행: "
              f"{df.loc[_unk, 'QuoteMethod'].value_counts().head().to_dict()}")
    print(f"      신뢰등급: {df.QuoteConfidence.value_counts().to_dict()}")

    print("[4/4] 저장")
    # T16: 최종 경로에 직접 쓰면 도중에 죽었을 때 새 것도 없고 직전 것도 없다.
    # CSV 쪽이 특히 위험했다 — 옛 코드는 기존 파일을 먼저 지우고 청크를 이어 붙였다.
    tmp_pq = OUT_PARQUET.with_suffix(".parquet.tmp")
    tmp_csv = OUT_CSV.with_suffix(".csv.tmp")
    try:
        df.to_parquet(tmp_pq, index=False, compression="zstd")
        if tmp_csv.exists():
            tmp_csv.unlink()
        for i in range(0, len(df), CHUNK):
            df.iloc[i:i + CHUNK].to_csv(tmp_csv, mode="a", header=(i == 0),
                                        index=False, encoding="utf-8-sig")
        os.replace(tmp_pq, OUT_PARQUET)
        os.replace(tmp_csv, OUT_CSV)
    except BaseException:
        tmp_pq.unlink(missing_ok=True)
        tmp_csv.unlink(missing_ok=True)
        raise

    # ------------------------------------------------------------- 리포트
    print("\n" + "=" * 74)
    print("복원 리포트")
    print("=" * 74)
    q = df["QuoteRaw"].notna()
    print(f"  축약 호가 있는 행        {int(q.sum()):,}")
    print(f"  민평 매칭된 행           {int((q & df.MPYieldDB.notna()).sum()):,} "
          f"({(q & df.MPYieldDB.notna()).sum() / max(q.sum(), 1) * 100:.1f}%)")
    # 경로가 둘이라 한 분모로 묶으면 지표가 거짓말한다(한때 108.5% 가 찍혔다).
    # 축약호가 복원과 «민평+원 스프레드» 를 갈라서 낸다.
    rest = df.QuoteYield.notna() & ~df.QuoteMethod.isin(
        ["spread_won", "over_under", "mp_plus_bp", "stated_abs", "at_mp"])
    print(f"  축약호가 복원 성공       {int(rest.sum()):,} "
          f"({rest.sum() / max(q.sum(), 1) * 100:.1f}% of 축약호가 행)")
    print(f"  QuoteYield 확정 합계     {int(df.QuoteYield.notna().sum()):,}")
    print(f"\n  복원 방식 분포")
    for k, v in df.QuoteMethod.value_counts().items():
        print(f"    {k:<12} {v:>10,}")
    print(f"\n  민평 대비 (bp) — 방식별")
    for k in df.QuoteMethod.dropna().unique():
        v = df.loc[df.QuoteMethod.eq(k), "QuoteVsMP_bp"].dropna()
        if not len(v):
            continue
        print(f"    {k:<12} n={len(v):>9,}  중앙 {v.median():+.2f}bp  "
              f"1bp {100*(v.abs()<=1).mean():5.1f}%  5bp {100*(v.abs()<=5).mean():5.1f}%")
    ok = df[rest]
    print("\n  틱 방향별 민평 대비 (사자(+)가 민평보다 금리 높아야 정상)")
    for tk in ("+", "-"):
        s = ok[ok.Tick == tk]
        if len(s):
            print(f"    Tick {tk}  n={len(s):>9,}  중앙 {s.QuoteVsMP_bp.median():+6.2f}bp")
    print("\n" + "-" * 74)
    print("  '원' 호가 bp 환산 [OWNER 자료 규칙]")
    w = df[df.SpreadUnit == "원"]
    print(f"    '원' 표기 행            {len(w):,}")
    print(f"    잔존만기 확보           {int(w.TTM_years.notna().sum()):,} "
          f"({w.TTM_years.notna().mean() * 100:.1f}%)  중앙값 {w.TTM_years.median():.2f}년")
    print(f"    bp 환산 성공            {int(df.SpreadBpEst.notna().sum()):,} "
          f"(원 {int(w.SpreadBpEst.notna().sum()):,} + bp표기 {int((df.SpreadUnit == 'bp').sum()):,})")
    ww = w[w.SpreadBpEst.notna()]
    print(f"    환산된 |bp| 중앙값      {ww.SpreadBpEst.abs().median():.2f}bp "
          f"(원 중앙 {ww.SpreadValue.abs().median():.2f}원)")
    print(f"    0.25원 배수 비율        "
          f"{np.isclose((w.SpreadValue.abs() * 4) % 1, 0).mean() * 100:.2f}%")
    print(f"    민평 단가 끝전 확보     {int(df.MPPriceFrac.notna().sum()):,} "
          f"({df.MPPriceFrac.notna().mean() * 100:.1f}%)")

    print("\n  샘플")
    c = ["Date", "Room", "BondCode", "QuoteRaw", "Tick", "Position",
         "MPYieldDB", "QuoteYield", "QuoteMethod", "QuoteVsMP_bp"]
    s = ok[c].tail(8).copy()
    s["Date"] = s["Date"].dt.strftime("%Y-%m-%d")
    print(s.to_string(index=False))
    print(f"\n  소요 {time.time() - t0:,.0f}초   -> {OUT_PARQUET.name}, {OUT_CSV.name}")


if __name__ == "__main__":
    main()
