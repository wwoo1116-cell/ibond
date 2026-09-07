# -*- coding: utf-8 -*-
"""시가평가 3사평균 커브 적재 [OWNER 2026-09-07 「엑셀로 줄게」].

`Documents\국고채권포함.xlsx` — 인포맥스 내려받기. 여섯 커브가 «옆으로» 붙어 있다
(국민주택1·2·3종 · 국고채권 · 서울도시철도 · 지역개발채), 각 «일자 + 12 잔존구간».

★이게 §10 의 「국민주택 민평 소스 부재」를 닫는다. 소스가 없던 게 아니라
  종목별 민평이 없었을 뿐이고, 국민주택 1종은 5년물 월별 발행이라
  **회차(YY-MM)가 곧 발행 연월**이므로 잔존이 회차에서 계산된다 →
  잔존으로 이 커브를 읽으면 그 회차의 민평이 나온다.

산출: kbond_mkt_curve.parquet  [curve, date, tenor_y, yield]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

SRC = Path(r"C:\Users\infomax\Documents\국고채권포함.xlsx")
OUT = Path(r"C:\Users\infomax\Projects\data\kbond") / "kbond_mkt_curve.parquet"
# 열 이름 «N년이하» -> 연 단위. 구간 상단을 그 구간의 대표 만기로 본다.
TENOR = {"3월이하": 0.25, "6월이하": 0.5, "9월이하": 0.75, "1년이하": 1.0,
         "1.5년이하": 1.5, "2년이하": 2.0, "2.5년이하": 2.5, "3년이하": 3.0,
         "4년이하": 4.0, "5년이하": 5.0, "7년이하": 7.0, "10년이하": 10.0}


def load(src: Path = SRC) -> pd.DataFrame:
    raw = pd.read_excel(src, header=None)
    heads = [(j, str(v)) for j, v in enumerate(raw.iloc[1]) if pd.notna(v)]
    out = []
    for n, (j0, title) in enumerate(heads):
        j1 = heads[n + 1][0] if n + 1 < len(heads) else raw.shape[1]
        blk = raw.iloc[3:, j0:j1].copy()
        blk.columns = [str(x).replace("(당일)", "").strip() for x in raw.iloc[2, j0:j1]]
        blk = blk.rename(columns={blk.columns[0]: "date"})
        blk["date"] = pd.to_datetime(blk["date"], errors="coerce")
        blk = blk.dropna(subset=["date"])
        for c, ty in TENOR.items():
            if c not in blk.columns:
                continue
            v = pd.to_numeric(blk[c], errors="coerce")
            out.append(pd.DataFrame({"curve": title.replace("시가평가 3사평균 ", ""),
                                     "date": blk["date"], "tenor_y": ty, "yield": v}))
    df = pd.concat(out, ignore_index=True).dropna(subset=["yield"])
    return df.sort_values(["curve", "date", "tenor_y"]).reset_index(drop=True)


def interp(df: pd.DataFrame, curve: str) -> dict:
    """(date -> (테너배열, 금리배열)). 잔존으로 선형보간해 쓰라고 배열로 준다."""
    s = df[df.curve == curve]
    return {d: (g.tenor_y.to_numpy(), g["yield"].to_numpy())
            for d, g in s.groupby("date", sort=False)}


def yield_at(tbl: dict, date, ttm: float):
    g = tbl.get(date)
    if g is None or ttm is None or not np.isfinite(ttm):
        return np.nan
    x, y = g
    return float(np.interp(ttm, x, y))          # 양끝은 그대로 물린다(외삽 안 함)


def main() -> int:
    if not SRC.exists():
        sys.exit(f"[FATAL] 없음: {SRC}")
    df = load()
    df.to_parquet(OUT, compression="zstd", index=False)
    print(f"커브 {df.curve.nunique()}종 · {len(df):,}행 · "
          f"{df.date.min():%Y-%m-%d}~{df.date.max():%Y-%m-%d}")
    for c, g in df.groupby("curve"):
        print(f"  {c:14s} {len(g):7,}행 · 일자 {g.date.nunique():,} · 테너 {g.tenor_y.nunique()}")
    print(f"\n  -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
