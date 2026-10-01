# -*- coding: utf-8 -*-
"""시세 테이프의 «어제까지» — 국고 종목의 분 단위 매도·매수와 그날의 전일 민평. [2026-10-01]

[OWNER 2026-10-01] 「비드·애스크만 그리고 체결은 표시만. 현재가는 늘 우측, 과거는
옆으로. 어제자랑 이어서 최대 1년.」

왜 따로 굽는가
  라이브 서버의 `hist` 는 **오늘** 10초 표본이고 자정에 지워진다(2,500점 상한).
  어제까지는 원장 파케이(830만 행)에 있는데, 요청마다 거기서 한 종목을 걸러 내면
  수 초가 든다. 그래서 하루 한 번(`kbond_daily_update`) 종목·날짜·분 단위로 접어
  작은 파케이로 구워 두고, API 는 그것만 읽는다.

무엇을 굽나
  code · date · m(장중 분) · b(그 분의 마지막 매수) · a(그 분의 마지막 매도) · mp(그날의 전일 민평)
  - 국고(`Sector == '국고'`)만. 통안은 원장이 ISIN(`MSBCode`)으로 서 있고 화면은 만기일
    코드를 쓰며, 국주는 종목 코드가 없다 — 그 둘은 오늘치(라이브)만 보인다.
  - 분 안에서는 «나중 것이 지금» — 같은 분에 둘이 오면 뒤의 것.
  - ★고립 스파이크는 뺀다: 같은 사이드 앞뒤 3건의 중앙값에서 6bp 넘게 튄 값
    (핸들 오파싱 — 실측 2026-09-21 4.05 가 3.93 무리 안에 섰다). 이웃 셋 미만이면 안 뺀다.
  - 민평은 `MPYieldDB`(그날 쓰인 전일 민평)의 하루 중앙값.

사용
  python kbond_px_hist.py            # 굽기
  kbond_px_hist.hist('26-1', days=22, before='2026-10-01')   # API 가 부른다
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

BASE = Path(r"C:\Users\infomax\Projects\data\kbond")
SRC = BASE / "kbond_structured_data.parquet"
OUT = BASE / "kbond_px_hist.parquet"

SECTOR = "국고"
COLS = ["Date", "Time", "Sector", "BondCode", "Position", "QuoteYield", "MPYieldDB"]
SIDES = {"BUY": "b", "SELL": "a"}
SPIKE_BP = 0.06     # 이웃 중앙값에서 이보다 멀면 고립 스파이크
SPIKE_WIN = 7       # 자기 포함 7 = 앞 3 + 뒤 3
SPIKE_MIN = 4       # 이웃이 셋 미만이면 판단하지 않는다


# ── 순수 조각 — 시험이 이것을 잰다 ──────────────────────────────────────────

def minute_of(t: str) -> int:
    """'HH:MM:SS' → 장중 분."""
    h, m = t.split(":")[:2]
    return int(h) * 60 + int(m)


def drop_spikes(y: pd.Series) -> pd.Series:
    """한 (종목, 사이드) 의 시간순 값 — 고립 스파이크를 NaN 으로.

    자기를 포함한 창 7 의 중앙값에서 `SPIKE_BP` 넘게 벗어나면 뺀다. 자기가 들어가도
    중앙값은 이웃 쪽에 서므로 판정은 같다(이웃 여섯 중 하나가 튀어도 중앙값은 안 움직인다).
    """
    if len(y) < SPIKE_MIN:
        return y
    med = y.rolling(SPIKE_WIN, center=True, min_periods=SPIKE_MIN).median()
    bad = (y - med).abs() > SPIKE_BP
    return y.mask(bad)


def collapse(df: pd.DataFrame) -> pd.DataFrame:
    """원장 행(국고 사이드 호가) → 종목·날짜·분 한 행.

    입력 열: Date(datetime) · Time('HH:MM:SS') · BondCode · Position · QuoteYield · MPYieldDB
    출력 열: code · date('YYYY-MM-DD') · m · b · a · mp   (code, date, m 오름차순)
    """
    d = df[df["QuoteYield"].notna() & df["Position"].isin(SIDES) & df["BondCode"].notna()].copy()
    if d.empty:
        return pd.DataFrame(columns=["code", "date", "m", "b", "a", "mp"])
    d["code"] = d["BondCode"].astype(str)
    d["date"] = pd.to_datetime(d["Date"]).dt.strftime("%Y-%m-%d")
    d["m"] = d["Time"].map(minute_of).astype("int32")
    d["side"] = d["Position"].map(SIDES)
    d = d.sort_values(["code", "date", "m", "Time"], kind="stable")

    # 분 안에서는 나중 것이 지금
    last = d.groupby(["code", "side", "date", "m"], sort=False)["QuoteYield"].last()
    last = last.reset_index().sort_values(["code", "side", "date", "m"], kind="stable")
    # 고립 스파이크 — (종목, 사이드) 시간순에서
    last["QuoteYield"] = last.groupby(["code", "side"], sort=False)["QuoteYield"].transform(drop_spikes)
    last = last[last["QuoteYield"].notna()]
    wide = (last.pivot_table(index=["code", "date", "m"], columns="side", values="QuoteYield", aggfunc="first")
            .reset_index())
    for c in ("b", "a"):
        if c not in wide.columns:
            wide[c] = pd.NA
    # 그날의 전일 민평 — 하루 중앙값
    mp = d.groupby(["code", "date"], sort=False)["MPYieldDB"].median().rename("mp").reset_index()
    out = wide.merge(mp, on=["code", "date"], how="left")
    out = out[["code", "date", "m", "b", "a", "mp"]].sort_values(["code", "date", "m"], kind="stable")
    out["m"] = out["m"].astype("int32")
    return out.reset_index(drop=True)


def slice_days(days: list[str], rows: list[list], mp: list, n: int, before: str | None) -> dict:
    """마지막 n 영업일(0 = 전부)만, `before`(exclusive) 앞의 날만.

    rows 의 첫 칸은 `days` 의 순번이다 — 잘라 낸 뒤 0 부터 다시 센다.
    """
    keep = [i for i, d in enumerate(days) if before is None or d < before]
    if n > 0:
        keep = keep[-n:]
    if not keep:
        return {"days": [], "q": [], "mp": []}
    lo = keep[0]
    ks = set(keep)
    q = [[r[0] - lo, r[1], r[2], r[3]] for r in rows if r[0] in ks]
    return {"days": [days[i] for i in keep], "q": q, "mp": [mp[i] for i in keep]}


# ── 굽기 ───────────────────────────────────────────────────────────────────

def bake() -> pd.DataFrame:
    t0 = time.time()
    tbl = pq.read_table(SRC, columns=COLS, filters=[("Sector", "==", SECTOR)])
    df = tbl.to_pandas()
    out = collapse(df)
    tmp = OUT.with_suffix(".parquet.tmp")
    out.to_parquet(tmp, compression="zstd", index=False)
    os.replace(tmp, OUT)
    print(f"  시세 테이프 {len(out):,}행 · 종목 {out['code'].nunique():,} · "
          f"{out['date'].min()}~{out['date'].max()} -> {OUT.name} "
          f"({OUT.stat().st_size / 2 ** 10:,.0f} KB) {time.time() - t0:,.0f}초")
    return out


def main() -> int:
    if not SRC.exists():
        sys.exit(f"[FATAL] 없음: {SRC}")
    bake()
    return 0


# ── 읽기 — API 가 쓴다. 파일이 바뀌면(아침 굽기) 다시 읽는다 ──────────────────

_CACHE: dict = {"mtime": None, "by_code": {}}


def _load() -> dict:
    if not OUT.exists():
        return {}
    mt = OUT.stat().st_mtime
    if _CACHE["mtime"] == mt:
        return _CACHE["by_code"]
    df = pd.read_parquet(OUT)
    by: dict[str, dict] = {}
    for code, g in df.groupby("code", sort=False):
        days = sorted(g["date"].unique().tolist())
        di = {d: i for i, d in enumerate(days)}
        mpd = g.groupby("date")["mp"].first()
        b = g["b"].astype(object).where(g["b"].notna(), None)
        a = g["a"].astype(object).where(g["a"].notna(), None)
        rows = [[di[d], int(m), bb, aa] for d, m, bb, aa in zip(g["date"], g["m"], b, a)]
        by[code] = {
            "days": days,
            "rows": rows,
            "mp": [None if pd.isna(mpd.get(d)) else float(mpd.get(d)) for d in days],
        }
    _CACHE["mtime"] = mt
    _CACHE["by_code"] = by
    return by


def hist(code: str, days: int = 22, before: str | None = None) -> dict:
    """`/api/px_hist` 의 몸통. 없는 종목이면 빈 날들 + note."""
    if before is None:
        before = dt.date.today().isoformat()
    by = _load()
    src = by.get(code)
    if not src:
        return {"code": code, "days": [], "q": [], "mp": [], "asof": None,
                "note": "이력이 없는 종목입니다 — 국고만 어제까지가 있습니다"}
    out = slice_days(src["days"], src["rows"], src["mp"], days, before)
    return {"code": code, **out, "asof": out["days"][-1] if out["days"] else None, "note": None}


if __name__ == "__main__":
    sys.exit(main())
