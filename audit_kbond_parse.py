# -*- coding: utf-8 -*-
"""
파싱 정확도 감사.

"몇 %가 맞았나"를 사람 손으로 8백만 행 대조할 수는 없으니, **원문으로
되짚어 확인할 수 있는 것만** 센다. 세 갈래다.

  A. 정밀도(precision)  뽑아 놓은 값이 원문에 실제로 있는가.
                        없으면 그 컬럼은 원문에 없는 값을 지어낸 것이다.
  B. 재현율(recall)     원문에 그 정보가 있어 보이는데 컬럼이 비었는가.
  C. 교차검증           서로 독립인 두 신호가 같은 답을 내는가.
                        (명시어 포지션 대 틱 포지션, 스프레드 부호 대 실제 금리차,
                         복원 금리 대 DB 민평)

D 로 무작위 표본을 찍어 눈으로 볼 수 있게 남긴다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(r"C:\Users\infomax\Projects\data\kbond")
PARQUET = BASE / "kbond_structured_data.parquet"
SAMPLE_OUT = BASE / "kbond_audit_sample.csv"
N_SAMPLE = 500
SEED = 20260827

RE_TICK = re.compile(r'(?<=\d)\s*([+\-])(?=\s|$|[^\d\-+])')
RE_SELL = re.compile(r'팔자|매도|팔고|당팔|셋팔|세트팔')
RE_BUY = re.compile(r'사자|매수|사고|당사|셋사|세트사')


def pct(n, d):
    return f"{100 * n / d:6.2f}%" if d else "   n/a"


def hdr(t):
    print("\n" + "=" * 76)
    print(t)
    print("=" * 76)


def main():
    if not PARQUET.exists():
        sys.exit(f"[FATAL] 없음: {PARQUET}")
    print(f"적재 {PARQUET}")
    df = pd.read_parquet(PARQUET)
    n = len(df)
    print(f"  {n:,}행 x {df.shape[1]}열")
    msg = df["Message"].fillna("")

    # ---------------------------------------------------------- A. 정밀도
    hdr("A. 정밀도 — 뽑은 값이 원문에 실제로 있는가")
    checks = {}

    def contains(col, transform=lambda s: s):
        m = df[col].notna()
        if not m.any():
            return None
        vals = transform(df.loc[m, col].astype(str))
        ok = [v in t for v, t in zip(vals, msg[m])]
        return m.sum(), int(np.sum(ok))

    for col in ["BondCode", "SeriesNo", "BondName", "Broker", "QuoteRaw", "Maturity"]:
        r = contains(col)
        if r:
            checks[col] = r
            print(f"  {col:<12} 값 있는 행 {r[0]:>9,}  원문에서 확인 {r[1]:>9,}  {pct(r[1], r[0])}")

    # 숫자 컬럼은 표기 변형이 있어 느슨하게 본다(3.802 / 3.80 / 802)
    for col, fmt in [("MPYield", "{:g}"), ("AbsYield", "{:g}"), ("Amount", "{:g}")]:
        m = df[col].notna()
        vals = df.loc[m, col]
        ok = [fmt.format(v) in t or fmt.format(v).lstrip("0") in t
              for v, t in zip(vals, msg[m])]
        checks[col] = (int(m.sum()), int(np.sum(ok)))
        print(f"  {col:<12} 값 있는 행 {int(m.sum()):>9,}  원문에서 확인 {int(np.sum(ok)):>9,}  "
              f"{pct(int(np.sum(ok)), int(m.sum()))}")

    # ---------------------------------------------------------- B. 재현율
    hdr("B. 재현율 — 원문에 있어 보이는데 컬럼이 빈 경우")
    sig = {
        "Amount":  msg.str.contains(r'\d\s*억', regex=True),
        "MPYield": msg.str.contains(r'민\s*[~≈]?\s*\d\.\d{2}', regex=True),
        "Broker":  msg.str.contains(r'\d{3,4}\s*[-.]\s*\d{4}', regex=True),
        "Position": msg.str.contains(r'팔자|사자|매도|매수|교체', regex=True),
        "Maturity": msg.str.contains(r'(?<![\d.])\d{2}\.\d{1,2}\.\d{1,2}(?![\d])', regex=True),
    }
    for col, s in sig.items():
        miss = int((s & df[col].isna()).sum())
        print(f"  {col:<10} 신호 있는 행 {int(s.sum()):>9,}  그중 결측 {miss:>9,}  "
              f"누락률 {pct(miss, int(s.sum()))}")

    # -------------------------------------------------------- C. 교차검증
    hdr("C. 교차검증 — 독립인 두 신호가 같은 답을 내는가")

    # C1. 명시어 포지션 대 틱 포지션 (둘 다 있는 행만)
    has_tick = msg.str.contains(RE_TICK)
    word = np.where(msg.str.contains(RE_SELL), "SELL",
                    np.where(msg.str.contains(RE_BUY), "BUY", None))
    tick = msg.str.extract(RE_TICK, expand=False).map({"-": "SELL", "+": "BUY"})
    both = pd.notna(word) & tick.notna()
    agree = int((pd.Series(word)[both].to_numpy() == tick[both].to_numpy()).sum())
    print(f"  C1 명시어 vs 틱   둘 다 있는 행 {int(both.sum()):>9,}  일치 {agree:>9,}  "
          f"{pct(agree, int(both.sum()))}")
    print("     (틱 규약 '-'=팔자/'+'=사자 가 맞다면 이 값이 높아야 한다)")

    # C2. 스프레드 부호 대 실제 금리차
    c2 = df[df.SpreadValue.notna() & df.MPYield.notna() & df.AbsYield.notna()].copy()
    c2["d"] = (c2.AbsYield - c2.MPYield) * 100
    c2 = c2[c2.d.abs() < 60]
    for unit, expect in [("원", -1), ("bp", 1)]:
        s = c2[(c2.SpreadUnit == unit) & (c2.SpreadValue != 0)]
        if len(s):
            ok = int((np.sign(s.d) == expect * np.sign(s.SpreadValue)).sum())
            lab = "가격단위(부호반대)" if unit == "원" else "금리단위(부호같음)"
            print(f"  C2 스프레드 '{unit}'  n={len(s):>9,}  {lab} 일치 {ok:>9,}  {pct(ok, len(s))}")

    # C3. 복원 금리 대 DB 민평
    if "QuoteYield" in df.columns:
        q = df[df.QuoteYield.notna()]
        print(f"  C3 복원금리 vs DB민평  n={len(q):>9,}  "
              f"|차이|<=1bp {pct(int((q.QuoteVsMP_bp.abs() <= 1).sum()), len(q))}  "
              f"<=5bp {pct(int((q.QuoteVsMP_bp.abs() <= 5).sum()), len(q))}")

    # C4. 본문에서 읽은 민평 대 DB 민평 (완전히 독립인 두 출처)
    if "MPYieldDB" in df.columns:
        # 코드 충돌(MBS 20-5 등)로 폐기한 행은 이미 MPYieldDB 가 비어 있다.
        c4 = df[df.MPYield.notna() & df.MPYieldDB.notna()]
        d = (c4.MPYield - c4.MPYieldDB).abs() * 100
        print(f"  C4 본문민평 vs DB민평  n={len(c4):>9,}  "
              f"|차이|<=1bp {pct(int((d <= 1).sum()), len(c4))}  "
              f"<=5bp {pct(int((d <= 5).sum()), len(c4))}  중앙 {d.median():.2f}bp")
        if "CodeCollision" in df.columns:
            print(f"     (2차 안전망이 버린 {int(df.CodeCollision.sum()):,}행은 제외된 상태)")

    # --------------------------------------------------------- D. 표본
    hdr(f"D. 무작위 표본 {N_SAMPLE}행 -> {SAMPLE_OUT.name}")
    smp = df.sample(N_SAMPLE, random_state=SEED)
    cols = ["Date", "Time", "Room", "Sender", "Message", "MsgType", "Position",
            "PositionSource", "Tick", "Sector", "BondCode", "SeriesNo", "BondName", "Maturity",
            "TTM_years", "MPYield", "MPYieldDB", "SpreadValue", "SpreadUnit",
            "SpreadBpEst", "AbsYield", "QuoteRaw", "QuoteYield", "Amount",
            "AmountImplied", "OddLot", "Broker"]
    cols = [c for c in cols if c in smp.columns]
    smp[cols].to_csv(SAMPLE_OUT, index=False, encoding="utf-8-sig")
    print(f"  저장 완료. 아래는 호가로 판정된 것 중 12행이다.\n")
    show = smp[smp.MsgType == "QUOTE"].head(12)
    for _, r in show.iterrows():
        print(f"  원문 | {str(r.Message)[:96]}")
        print(f"       -> {r.Position}/{r.PositionSource} {r.Sector} "
              f"code={r.BondCode} name={r.BondName} 만기={r.Maturity} "
              f"민평={r.MPYield} 호가={r.QuoteRaw} 스프레드={r.SpreadValue}{r.SpreadUnit or ''} "
              f"수량={r.Amount}")

    hdr("종합")
    tp = sum(v[1] for v in checks.values())
    td = sum(v[0] for v in checks.values())
    print(f"  A 정밀도 가중평균 : {pct(tp, td)}  ({tp:,}/{td:,})")
    print(f"  표본 CSV          : {SAMPLE_OUT}")


if __name__ == "__main__":
    main()
