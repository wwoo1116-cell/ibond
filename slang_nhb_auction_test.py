# -*- coding: utf-8 -*-
"""국당·국전·국전전·국딱 판별: 국민주택인가 국채인가, 그리고 그날 입찰이 가르는가.

[OWNER 2026-09-03] 「국당 국딱 같은거 국민주택이랑 국채를 혼용하는거래,
그 날 국채입찰일인지, 국민주택입찰일인지 마다 다를듯?」

검정 설계 — 축약호가는 «소수부» 다. 후보 기준금리에 restore 를 걸어
|복원값 − 기준| <= 5bp 면 적중으로 본다(이 레인이 통안 은어를 해독할 때 쓴 것과
같은 판별자). 두 가설을 같은 행에 동시에 걸고 적중률을 비교한다.

  H_NHB  국민주택 1종 = 국고 5Y 지표물 민평 + 15.7bp (기존 연구가 찾은 오프셋)
  H_AUC  그날 입찰된 국고채 = load_auction 의 민평/낙찰금리

그리고 **그날이 국채 입찰일인가** 로 표본을 갈라 둘을 따로 센다.
오너 가설이 맞다면: 입찰일에는 H_AUC 가, 비입찰일에는 H_NHB 가 이겨야 한다.
"""
from __future__ import annotations
import sys, re
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from enrich_kbond_quotes import engine, restore, load_auction, norm_code
from sqlalchemy import text

PARQUET = Path(r"C:\Users\infomax\Projects\data\kbond\kbond_structured_data.parquet")
SLANG = ["국전전", "국전당", "국당", "국전", "국딱"]
NHB_OFFSET = 0.157        # 기존 연구: 국주 문면 호가 중심 +15.7bp (5Y 지표 대비)
HIT = 0.05                # 5bp


def main():
    cols = ["Date", "Message", "MsgType", "Sector", "QuoteRaw", "Position",
            "BondCode", "MPYield"]
    print("[1/5] 적재")
    df = pd.read_parquet(PARQUET, columns=cols)
    df = df[df["QuoteRaw"].notna() & df["MsgType"].eq("QUOTE")]
    print(f"      호가 {len(df):,}행")

    # 은어별로 가른다. 긴 낱말이 먼저 걸려야 한다.
    msg = df["Message"].astype(str)
    tag = pd.Series(index=df.index, dtype=object)
    for w in SLANG:
        m = msg.str.contains(w, na=False) & tag.isna()
        tag[m] = w
    df = df[tag.notna()].copy()
    df["slang"] = tag[tag.notna()]
    print(f"      은어 행 {len(df):,}  {df['slang'].value_counts().to_dict()}")

    print("[2/5] 국고 5Y 지표물 민평 (H_NHB 기준)")
    with engine().connect() as c:
        otr = pd.read_sql(text(
            "SELECT 일자, 만기, 종목명 FROM ontherun_schedule "
            "WHERE 변경내용='지표지정' AND 종목명 LIKE '국고%'"), c)
        mp = pd.read_sql(text(
            "SELECT 일자, 종목코드, 민평 FROM `국고통_민평` "
            "WHERE 종목코드 LIKE 'KR10%'"), c)
        m1 = pd.read_sql(text(
            "SELECT DISTINCT 종목명, 표준코드 FROM ontherun_schedule"), c)
        m2 = pd.read_sql(text(
            "SELECT 표준코드, 종목명 FROM `국채_발행정보` "
            "WHERE 종목명 REGEXP '^[0-9]{1,2}-[0-9]{1,2}$'"), c)
    otr["일자"] = pd.to_datetime(otr["일자"])
    otr["만기"] = pd.to_numeric(otr["만기"], errors="coerce")   # ★float 이다(5.0)
    otr["code"] = otr["종목명"].str.extract(r"[(](\d{2}-\d{1,2})[)]")
    otr = otr.dropna(subset=["code", "만기"]).sort_values("일자")
    m1["BondCode"] = m1["종목명"].str.extract(r'\((\d{2}-\d{1,2})\)')
    m1 = m1.dropna(subset=["BondCode"])
    m2 = m2.rename(columns={"종목명": "BondCode"})
    mm = pd.concat([m1[["BondCode", "표준코드"]], m2[["BondCode", "표준코드"]]])
    mm["BondCode"] = norm_code(mm["BondCode"])
    mm = mm.drop_duplicates("BondCode", keep="last")
    c2i = dict(zip(mm["BondCode"], mm["표준코드"]))
    mp["일자"] = pd.to_datetime(mp["일자"])
    mpmap = {(d, c_): v for d, c_, v in zip(mp["일자"], mp["종목코드"], mp["민평"])}

    # 날짜 -> 만기별 그 시점 지표물 민평. 후보를 하나로 좁히지 않고 전부 건다.
    days = pd.Index(sorted(df["Date"].dt.normalize().unique()))
    TEN = [2.0, 3.0, 5.0, 10.0, 20.0, 30.0]
    ref = {}                                   # 후보명 -> {날짜: 기준금리}
    for tn in TEN:
        g = otr[otr["만기"].eq(tn)]
        if not len(g):
            continue
        codes = norm_code(g["code"]).to_numpy()
        idx = np.searchsorted(g["일자"].values, days.values, side="right") - 1
        m = {}
        for k, i in zip(days, idx):
            if i < 0:
                continue
            isin = c2i.get(codes[i])
            v = mpmap.get((k, isin)) if isin else None
            if v is not None and pd.notna(v):
                m[k] = float(v)
        ref[f"국고{int(tn)}Y"] = m
    # 국민주택 1종 = 국고 5Y 지표 + 15.7bp (기존 연구가 찾은 오프셋)
    ref["국민주택"] = {k: v + NHB_OFFSET for k, v in ref.get("국고5Y", {}).items()}
    print(f"      지표물 기준 확보: " +
          " · ".join(f"{k} {len(v)}일" for k, v in ref.items()))

    print("[3/5] 그날 입찰물 (그날 낙찰된 국고채)")
    au = load_auction(df["Date"])
    ref["입찰물"] = {k: float(v) for k, v in au["mp"].items()
                   if v is not None and pd.notna(v)}
    auc_days = set(ref["입찰물"])

    print("[4/5] 복원 · 적중 판정")
    d0 = df["Date"].dt.normalize()
    df["is_auc"] = d0.isin(auc_days)
    for name, m in ref.items():
        r = d0.map(m)
        out, _ = restore(df["QuoteRaw"], r)
        df["hit_" + name] = np.abs(out - r) <= HIT
        df["has_" + name] = r.notna()


    print("[5/5] 결과")
    names = list(ref)
    rows = []
    for w in SLANG:
        g = df[df["slang"].eq(w)]
        for lab, gg in (("입찰일", g[g["is_auc"]]), ("비입찰일", g[~g["is_auc"]])):
            if not len(gg):
                continue
            r = {"은어": w, "그날": lab, "행": len(gg)}
            for nm in names:
                n = int(gg["has_" + nm].sum())
                r[nm] = (round(100 * gg["hit_" + nm].sum() / n, 1) if n else None)
            rows.append(r)
    res = pd.DataFrame(rows)
    txt = res.to_string(index=False)
    print(txt)
    print()
    print("(칸 값 = 그 기준으로 축약호가를 복원했을 때 5bp 적중률 %)")

    out = Path(__file__).parent / "RESULT_slang_nhb_auction.md"
    body = [
        "# 국당·국딱 판별 — 국민주택인가 국채인가 (2026-09-03)",
        "",
        "[OWNER 2026-09-03] 「국당 국딱 같은거 국민주택이랑 국채를 혼용하는거래,",
        "그 날 국채입찰일인지, 국민주택입찰일인지 마다 다를듯?」",
        "",
        f"판별자: |restore(축약호가, 기준) − 기준| <= {HIT * 100:.0f}bp 적중률(%).",
        "후보 기준을 같은 행에 전부 걸고 비교한다. 국민주택 = 국고 5Y 지표 + "
        f"{NHB_OFFSET * 100:.1f}bp (기존 연구 오프셋), 입찰물 = 그날 낙찰된 국고채.",
        "",
        "```",
        txt,
        "```",
        "",
    ]
    out.write_text("\n".join(body), encoding="utf-8")
    print()
    print(f"기록: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
