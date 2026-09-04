# -*- coding: utf-8 -*-
"""국고 은어 판별 2차 — 적중률이 아니라 «오프셋 분포» 로 본다.

## 1차가 왜 틀렸나

1차(`slang_ktb_discriminant.py`)는 복원값이 민평 5bp 이내인 비율을 셌다.
그런데 그 문턱은 **«만기가 틀렸다» 와 «만기는 맞는데 다른 종목이라 스프레드가
있다» 를 구분하지 못한다.** 은어가 국민주택채권이면 국고 대비 10bp 남짓 벌어져
있으므로, 만기를 정확히 맞혀도 5bp 문턱에서는 떨어진다. 실제로 1차는 배관검정
98.4% 대비 어느 칸도 46% 를 못 넘었고 국당·국전·국전전이 **전부 같은 칸**에
떨어졌다 — 신호가 아니라 잡음의 모양이다.

## 무엇을 대신 재는가

축약호가는 정수부를 민평에서 물려받고 **소수부만** 말한다. 그래서 정수부를
버리고 소수부만 비교하면 «호가 − 기준» 오프셋을 bp 로 얻을 수 있다.

    q = 축약호가의 소수부 (bp).  '66' -> 66.0 · '615' -> 61.5
    f = 후보 종목 민평의 소수부 (bp)
    s = (q - f) 를 (-50, +50] 로 감아 준 값

맞는 후보라면 s 는 **한 값 주위에 뭉친다**(0 일 필요가 없다 — 크레딧
스프레드만큼 치우쳐 있어도 된다). 틀린 후보라면 s 는 (-50,+50] 에 고르게 퍼진다.

판정 통계는 **원형 집중도** R = |mean(exp(2πi·s/100))| 이다. 고르면 0, 한 점에
뭉치면 1. 100bp 주기로 감기는 자료라 원형 통계가 맞는 도구다.
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

BASE = Path(r"C:\Users\infomax\Projects\data\kbond")
PARQUET = BASE / "kbond_structured_data.parquet"
CACHE = BASE / "slang_testable.parquet"      # 없으면 본표에서 만든다
OUT = Path(__file__).parent / "RESULT_ktb_slang_grid_offset.md"
# ⚠ RESULT_ktb_slang.md 는 손으로 쓴 분석 문서다. 스크립트가 덮으면 안 된다.

# 앞 경계만 건다. 뒤 경계를 넣으면 '국당팔고' 처럼 동사가 바로 붙는 진짜 호가가
# 잘린다. 앞 경계가 없으면 '한국전력'의 「국전」이 걸려 4분의 3이 가짜가 된다.
# 교대 순서는 길이 내림차순 — 안 그러면 '국전'이 '국전전'을 삼킨다.
RE_SLANG = re.compile(r'(?<![가-힣])(국전전|국전당|국당|국딱|국전)')


def build_cache() -> pd.DataFrame:
    """본표에서 검정 대상을 뽑는다.

    조건 셋: 은어가 하나만 든 메시지(둘이면 어느 쪽 호가인지 모른다) ·
    축약호가가 있음 · 종목코드가 없음(있으면 그 종목이 답이라 검정이 무의미).
    """
    import pyarrow.parquet as pq
    cols = ["Date", "Message", "Sector", "BondCode", "QuoteRaw"]
    src = pq.ParquetFile(PARQUET)
    parts = []
    for rg in range(src.num_row_groups):
        d = src.read_row_group(rg, columns=cols).to_pandas()
        d = d[d["Message"].astype(str).str.contains(RE_SLANG, na=False)]
        if len(d):
            parts.append(d)
    df = pd.concat(parts, ignore_index=True)
    hits = df["Message"].astype(str).map(RE_SLANG.findall)
    df["Slang"] = hits.map(lambda x: x[0])
    df = df[(hits.map(lambda x: len(set(x))) == 1)
            & df["QuoteRaw"].notna() & df["BondCode"].isna()].copy()
    df.to_parquet(CACHE, index=False)
    print(f"  캐시 생성 {CACHE.name} — {len(df):,}행")
    return df

MATURITIES = [2.0, 3.0, 5.0, 10.0, 20.0, 30.0, 50.0]
RANKS = [0, 1, 2]
MIN_N = 200


def engine():
    return create_engine(
        f"mysql+pymysql://{os.environ['BW_MYSQL_USER']}:{os.environ['BW_MYSQL_PASSWORD']}"
        f"@{os.environ['BW_MYSQL_HOST']}:{os.environ['BW_MYSQL_PORT']}"
        f"/infomax?charset=utf8mb4", pool_pre_ping=True)


def norm(s):
    return s.str.replace(r'^(\d{2})-0*(\d+)$', r'\1-\2', regex=True)


def quote_bp(raw: pd.Series) -> pd.Series:
    """축약호가 -> 소수부 bp. 양방 토큰 '405.41' 은 뒤 다리를 쓴다(복원기와 같은 규약)."""
    r = raw.astype(str)
    two = r.str.match(r'^\d{2,3}\.\d{2,3}$')
    r = r.where(~two, r.str.split(".").str[-1])
    d = r.str.replace(".", "", regex=False)
    n = d.str.len()
    v = pd.to_numeric(d, errors="coerce")
    return pd.Series(np.where(n == 2, v, np.where(n == 3, v / 10.0, np.nan)),
                     index=raw.index)


def circ(s: np.ndarray):
    """오프셋 배열 -> (집중도 R, 중심 bp, 중심 +-5bp 비율)."""
    if len(s) < 20:
        return np.nan, np.nan, np.nan
    a = 2 * np.pi * s / 100.0
    z = np.exp(1j * a).mean()
    R = abs(z)
    c = (np.angle(z) * 100 / (2 * np.pi))
    d = np.abs(((s - c + 50) % 100) - 50)
    return R, c, float((d <= 5).mean() * 100)


def load(d0, d1):
    with engine().connect() as c:
        otr = pd.read_sql(text(
            "SELECT 일자, 만기, 종목명, 표준코드 FROM ontherun_schedule "
            "WHERE 변경내용='지표지정'"), c)
        mp = pd.read_sql(text(
            "SELECT 일자, 종목코드, 민평 FROM `국고통_민평` "
            "WHERE 종목코드 LIKE 'KR10%' AND 일자 BETWEEN :a AND :b"),
            c, params={"a": str(d0), "b": str(d1)})
    otr = otr[otr["종목명"].str.startswith("국고")].copy()
    otr["일자"] = pd.to_datetime(otr["일자"])
    otr = otr.sort_values("일자")
    mp["일자"] = pd.to_datetime(mp["일자"])
    mp = mp[mp["민평"].between(0.3, 9)]
    return otr, mp


def rung(otr, mat, rank, dates):
    g = otr[otr["만기"].eq(mat)]
    if not len(g):
        return pd.Series(index=dates, dtype=object)
    ed, ec = g["일자"].to_numpy(), g["표준코드"].to_numpy()
    pos = np.searchsorted(ed, dates.to_numpy(), side="right") - 1 - rank
    return pd.Series(np.where(pos >= 0, ec[np.clip(pos, 0, None)], None),
                     index=dates, dtype=object)


def main():
    t0 = time.time()
    df = pd.read_parquet(CACHE) if CACHE.exists() else build_cache()
    df["Date"] = pd.to_datetime(df["Date"])
    df["qbp"] = quote_bp(df["QuoteRaw"])
    df = df[df["qbp"].notna()]
    print(f"[1/3] 대상 {len(df):,}행")

    otr, mp = load(df.Date.min().date(), df.Date.max().date())
    mpmap = {(d, c): v for d, c, v in zip(mp["일자"], mp["종목코드"], mp["민평"])}
    dates = pd.Index(sorted(df["Date"].unique()))
    rungs = {(m, r): rung(otr, m, r, dates) for m in MATURITIES for r in RANKS}
    print(f"[2/3] 사다리 · 민평 {len(mp):,}행")

    print("[3/3] 격자")
    rows = []
    for slang, g in df.groupby("Slang"):
        for m in MATURITIES:
            for r in RANKS:
                isin = rungs[(m, r)].reindex(g["Date"]).to_numpy()
                base = np.array([mpmap.get(k, np.nan)
                                 for k in zip(g["Date"], isin)], dtype=float)
                ok = np.isfinite(base)
                if ok.sum() < MIN_N:
                    continue
                fb = (base[ok] % 1.0) * 100.0
                s = ((g["qbp"].to_numpy()[ok] - fb + 50) % 100) - 50
                R, c, near = circ(s)
                rows.append(dict(Slang=slang, 만기=m, 순위=r, n=int(ok.sum()),
                                 R=R, 중심=c, 중심5bp=near))
    grid = pd.DataFrame(rows)
    report(df, grid, time.time() - t0)
    return 0


def report(df, grid, secs):
    L, A = [], None
    A = L.append
    A("# 국고 은어 판별 — 오프셋 분포")
    A("")
    A(f"실행 2026-09-02 · {len(df):,}행 · {df.Date.min().date()} ~ "
      f"{df.Date.max().date()} · {secs:,.0f}초")
    A("")
    A("판정 통계는 **원형 집중도 R** 이다(고르면 0, 한 점에 뭉치면 1).")
    A("«중심» 은 그 뭉침의 위치로, 호가가 그 종목 민평보다 몇 bp 높은지를 뜻한다.")
    A("중심이 0 일 필요는 없다 — 다른 종목이면 스프레드만큼 치우쳐 있는 게 정상이다.")
    A("")
    for slang, g in grid.groupby("Slang"):
        A(f"## `{slang}`  (n={int(g['n'].max()):,})")
        A("")
        piv = g.pivot(index="만기", columns="순위", values="R")
        A("원형 집중도 R — 행=만기, 열=순위")
        A("")
        A("| 만기 | " + " | ".join(f"r{c}" for c in piv.columns) + " |")
        A("|---|" + "---|" * len(piv.columns))
        for m, row in piv.iterrows():
            A(f"| {m:.0f}Y | " + " | ".join(
                "—" if pd.isna(v) else f"{v:.3f}" for v in row) + " |")
        A("")
        b = g.sort_values("R", ascending=False).iloc[0]
        r2 = g.sort_values("R", ascending=False).iloc[1]
        A(f"1등 **{b['만기']:.0f}Y r{int(b['순위'])}**  R=**{b['R']:.3f}** · "
          f"중심 **{b['중심']:+.1f}bp** · 중심 ±5bp 안 {b['중심5bp']:.1f}% · n={int(b['n']):,}")
        A(f"2등 {r2['만기']:.0f}Y r{int(r2['순위'])}  R={r2['R']:.3f} · "
          f"중심 {r2['중심']:+.1f}bp")
        A("")
    OUT.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    print(f"\n  -> {OUT}")


if __name__ == "__main__":
    sys.exit(main())
