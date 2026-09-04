# -*- coding: utf-8 -*-
"""국고 은어(국당·국전·국전전·국전당·국딱) 만기 판별검정.

## 왜 이 검정인가

국고 은어에는 만기가 안 적힌다(오너 지적). 통안은 «구»=한 단계 이전, «삼»=3년물
이라는 문법을 판별검정으로 확정했는데, 국고도 같은 수법이 통한다.

원리는 **축약호가의 소수부**다. `국당 66-` 의 '66' 은 민평의 정수부를 물려받고
소수부만 말한다. 만기를 잘못 짚으면 그 만기 지표물의 민평 소수부와 안 맞으므로
복원 잔차가 커진다. 만기가 맞으면 호가는 민평 근처에 있으므로 잔차가 작다.
2자리 토큰은 1bp, 3자리는 0.1bp 해상도라 5bp 문턱에서 판별력이 나온다.

## 무엇을 재는가

만기 7종 x 순위 4종 = 28칸을 은어마다 전부 돌린다. **순위 가정도 검정 대상이다**
— 국당=r0·국전=r1 은 «당월/전월» 해석에서 나온 가설이지 확인된 사실이 아니다.

## 배관검정을 먼저 한다

지표코드가 문면에 적힌 행(`24-8 66-`)을 같은 복원기로 돌려 적중률 상한을 잰다.
이걸 안 하면 은어 적중률이 낮게 나왔을 때 «은어가 틀렸다» 인지 «복원기가 안 된다»
인지 못 가린다. 부재는 합격이 아니다.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent))
from enrich_kbond_quotes import restore, norm_code          # noqa: E402

# 입력은 2차 스크립트와 공유한다(없으면 거기서 본표를 훑어 만든다).
from slang_ktb_offset import CACHE, build_cache                # noqa: E402
OUT = Path(__file__).parent / "RESULT_ktb_slang_grid_hitrate.md"
# ⚠ RESULT_ktb_slang.md 는 손으로 쓴 분석 문서다. 스크립트가 덮으면 안 된다.

MATURITIES = [2.0, 3.0, 5.0, 10.0, 20.0, 30.0, 50.0]
RANKS = [0, 1, 2, 3]
HIT_BP = 5.0            # 적중 문턱
MIN_N = 200             # 이보다 표본이 적은 칸은 순위에서 뺀다


def engine():
    need = ["BW_MYSQL_HOST", "BW_MYSQL_PORT", "BW_MYSQL_USER", "BW_MYSQL_PASSWORD"]
    miss = [k for k in need if not os.environ.get(k)]
    if miss:
        sys.exit(f"[FATAL] 환경변수 미설정: {miss}")
    return create_engine(
        f"mysql+pymysql://{os.environ['BW_MYSQL_USER']}:{os.environ['BW_MYSQL_PASSWORD']}"
        f"@{os.environ['BW_MYSQL_HOST']}:{os.environ['BW_MYSQL_PORT']}"
        f"/infomax?charset=utf8mb4", pool_pre_ping=True)


def load_ladder(d0, d1):
    """«날짜 x 만기 -> 순위별 ISIN» 사다리 + 민평.

    지표지정 이력을 만기별로 시간순 정렬해 두고, 어떤 날짜에 대해
    그날 이전(당일 포함) 마지막 지표지정이 r0, 그 앞이 r1 … 이다.
    """
    with engine().connect() as c:
        otr = pd.read_sql(text(
            "SELECT 일자, 변경내용, 만기, 종목명, 표준코드 FROM ontherun_schedule "
            "WHERE 변경내용 = '지표지정'"), c)
        mp = pd.read_sql(text(
            "SELECT 일자, 종목코드, 민평 FROM `국고통_민평` "
            "WHERE 종목코드 LIKE 'KR10%' AND 일자 BETWEEN :a AND :b"),
            c, params={"a": str(d0), "b": str(d1)})

    # ★물가채가 만기 10 에 섞여 있다. 종목명 머리로 국고만 남긴다.
    n_all = len(otr)
    otr = otr[otr["종목명"].str.startswith("국고")].copy()
    print(f"  지표지정 이력 {n_all:,} -> 국고만 {len(otr):,}"
          f" (물가·기타 {n_all - len(otr):,} 제외)")
    otr["일자"] = pd.to_datetime(otr["일자"])
    otr["BondCode"] = otr["종목명"].str.extract(r'\((\d{2}-\d{1,2})\)')[0].pipe(norm_code)
    otr = otr.sort_values("일자")

    mp["일자"] = pd.to_datetime(mp["일자"])
    mp = mp[mp["민평"].between(0.3, 9)]
    print(f"  국고 민평 {len(mp):,}행 · 종목 {mp['종목코드'].nunique():,}종")
    return otr, mp


def rung(otr, mat, rank, dates):
    """만기 mat 의 rank 번째 지표물 ISIN 을 날짜별로 준다."""
    g = otr[otr["만기"].eq(mat)]
    if not len(g):
        return pd.Series(index=dates, dtype=object)
    ev_d = g["일자"].to_numpy()
    ev_c = g["표준코드"].to_numpy()
    # 각 날짜에 대해 그 날짜 이하 마지막 사건의 위치
    pos = np.searchsorted(ev_d, dates.to_numpy(), side="right") - 1 - rank
    out = np.where(pos >= 0, ev_c[np.clip(pos, 0, None)], None)
    return pd.Series(out, index=dates, dtype=object)


def score(df, mpmap, isin_by_row):
    """복원 잔차와 적중률. isin_by_row 가 None 인 행은 버린다."""
    key = list(zip(df["Date"], isin_by_row))
    mp = pd.Series([mpmap.get(k, np.nan) for k in key], index=df.index)
    ok = mp.notna() & df["QuoteRaw"].notna()
    if ok.sum() < 20:
        return dict(n=int(ok.sum()), hit=np.nan, med=np.nan)
    y, _ = restore(df.loc[ok, "QuoteRaw"], mp[ok])
    diff = (pd.Series(y, index=mp[ok].index) - mp[ok]).abs() * 100.0   # bp
    d = diff.dropna()
    return dict(n=int(len(d)),
                hit=float((d <= HIT_BP).mean() * 100) if len(d) else np.nan,
                med=float(d.median()) if len(d) else np.nan)


def main():
    t0 = time.time()
    df = pd.read_parquet(CACHE) if CACHE.exists() else build_cache()
    df["Date"] = pd.to_datetime(df["Date"])
    print(f"[1/4] 검정 대상 {len(df):,}행  {df.Date.min().date()} ~ {df.Date.max().date()}")

    print("[2/4] 사다리")
    otr, mp = load_ladder(df.Date.min().date(), df.Date.max().date())
    mpmap = {(d, c): v for d, c, v in
             zip(mp["일자"], mp["종목코드"], mp["민평"])}

    dates = pd.Index(sorted(df["Date"].unique()))
    rungs = {(m, r): rung(otr, m, r, dates) for m in MATURITIES for r in RANKS}

    print("[3/4] 배관검정 — 지표코드가 문면에 적힌 행")
    plumb = plumbing(mpmap, otr)

    print("[4/4] 격자")
    rows = []
    for slang, g in df.groupby("Slang"):
        for m in MATURITIES:
            for r in RANKS:
                s = rungs[(m, r)].reindex(g["Date"]).to_numpy()
                res = score(g, mpmap, s)
                rows.append(dict(Slang=slang, 만기=m, 순위=r, **res))
    grid = pd.DataFrame(rows)
    report(df, grid, plumb, time.time() - t0)
    return 0


def plumbing(mpmap, otr):
    """지표코드 명시 행으로 복원기 상한을 잰다(은어와 같은 복원기·같은 문턱)."""
    import pyarrow.parquet as pq
    P = Path(r"C:\Users\infomax\Projects\data\kbond\kbond_structured_data.parquet")
    cols = ["Date", "BondCode", "QuoteRaw", "Sector"]
    code2isin = (otr.dropna(subset=["BondCode"])
                 .drop_duplicates("BondCode", keep="last")
                 .set_index("BondCode")["표준코드"].to_dict())
    src = pq.ParquetFile(P)
    parts = []
    for rg in range(src.num_row_groups):
        d = src.read_row_group(rg, columns=cols).to_pandas()
        d = d[d["Sector"].eq("국고") & d["BondCode"].notna() & d["QuoteRaw"].notna()]
        if len(d):
            parts.append(d)
    d = pd.concat(parts, ignore_index=True)
    d["Date"] = pd.to_datetime(d["Date"])
    isin = d["BondCode"].map(code2isin)
    res = score(d, mpmap, isin)
    print(f"      지표코드 명시 {len(d):,}행 -> 민평 붙은 {res['n']:,}행 "
          f"· 5bp 적중 {res['hit']:.1f}% · 중앙 {res['med']:.2f}bp")
    return res


def report(df, grid, plumb, secs):
    L = []
    A = L.append
    A("# 국고 은어 만기 판별검정")
    A("")
    A(f"실행 2026-09-02 · 대상 {len(df):,}행 · {df.Date.min().date()} ~ "
      f"{df.Date.max().date()} · {secs:,.0f}초")
    A("")
    A("## 배관검정 (이걸 먼저 본다)")
    A("")
    A("지표코드가 문면에 적힌 국고 호가를 **같은 복원기·같은 문턱**으로 돌린 것이다.")
    A("은어 적중률은 이 값을 넘을 수 없다. 낮게 나온 칸이 «은어가 틀렸다» 인지")
    A("«복원기가 안 된다» 인지 가르는 기준선이다.")
    A("")
    A(f"- 표본 **{plumb['n']:,}행** · 5bp 적중 **{plumb['hit']:.1f}%** "
      f"· 잔차 중앙 **{plumb['med']:.2f}bp**")
    A("")
    for slang, g in grid.groupby("Slang"):
        g = g[g["n"] >= MIN_N]
        A(f"## `{slang}`")
        A("")
        if not len(g):
            A(f"표본이 모든 칸에서 {MIN_N}행 미만이라 판정하지 않는다.")
            A("")
            continue
        piv = g.pivot(index="만기", columns="순위", values="hit")
        A("5bp 적중률(%) — 행=만기, 열=순위(r0=당월·r1=전월·…)")
        A("")
        A("| 만기 | " + " | ".join(f"r{r}" for r in piv.columns) + " |")
        A("|---|" + "---|" * len(piv.columns))
        for m, row in piv.iterrows():
            A(f"| {m:.0f}Y | " + " | ".join(
                "—" if pd.isna(v) else f"{v:.1f}" for v in row) + " |")
        A("")
        best = g.sort_values("hit", ascending=False).iloc[0]
        rest = g.sort_values("hit", ascending=False).iloc[1]
        gap = best["hit"] - rest["hit"]
        A(f"1등 **{best['만기']:.0f}Y r{int(best['순위'])}** "
          f"적중 **{best['hit']:.1f}%** · 잔차 중앙 {best['med']:.2f}bp · n={int(best['n']):,}")
        A(f"2등 {rest['만기']:.0f}Y r{int(rest['순위'])} {rest['hit']:.1f}% "
          f"· **격차 {gap:.1f}%p**")
        A("")
    p = OUT
    p.write_text("\n".join(L), encoding="utf-8")
    print(f"\n  -> {p}")
    print("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
