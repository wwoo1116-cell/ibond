# -*- coding: utf-8 -*-
r"""잔존별 «싼 정도» 분포 — 「짧은 잔존의 큰 bp 는 돈인가 인공물인가」.

    python -X utf8 alarm_ttm.py > out.txt

## 왜 이 파일이 있나 [2026-10-01]

알람 문턱을 무리 중앙 대비 **3bp** 로 걸었더니 1등이 **잔존 0.01년에 +31.8bp**
(KB캐피탈533-4)였다. 그 만기에서 31bp 는 단가로 0.3원이다 — 싼 것이 아니라
**자가 늘어난 것**으로 보였다. 그 의심을 원장 전체로 재는 것이 이 파일이다.
판정은 `PROMPT_next_2026-09-30-alarm.md` §3½, 수는
`archive/docs/RESULT_alarm_ttm_2026-10-01.md`.

★**읽기만 한다.** 원장 parquet 를 읽고 아무것도 안 고친다. 산 서버도 안 건드린다.

## 자를 왜 이렇게 골랐나

· **모집단** — 크레딧 레인의 «값 부른 SELL 오퍼»(`Sector=='크레딧/기타'` · `AtMP=False`
  · `QuoteVsMP_bp` 있음 · 조회 아님). 알람이 보는 것과 같은 집합이다.
· **무리** — 알람의 무리는 계열×등급×잔존칸인데 **원장엔 등급이 안 붙는다**
  (`RatingCat` 이 이 행들에서 전건 결측 — 메시지 수준 열이다). 그래서 여기선
  **(날짜 × 잔존칸)** 으로 근사한다. 등급을 못 갈라 중앙이 더 시끄럽지만, 묻는 것은
  «같은 칸 안에서 잔존이 짧을수록 편차가 벌어지나» 라서 그 축은 보존된다.
  ⚠**정확한 자는 산 서버**다 — `alarm_sizing.py --calibrate` 가 진짜 무리로 낸다.
· **잔존칸** — `kbond_view.BUCKETS` 와 같은 것(맨 앞 칸이 `~1년` 이다. 잔존 사흘짜리와
  잔존 열한 달짜리가 **같은 중앙과 비교된다** — 이 물음이 생긴 자리가 바로 거기다).
· **환산** — `alarm_sizing.bp_per_won` 하나만 쓴다(그것이 `enrich_kbond_quotes` 의
  실측표를 읽는다). 수치를 여기 베끼지 않는다 — 두 벌로 두면 한쪽만 고치게 된다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from enrich_kbond_quotes import PARQUET

#: 도착 수·무리 최소·원↔bp 환산은 **한 곳에서만** 유도한다 — 두 벌로 두면 한쪽만 고치게 된다.
from alarm_sizing import ARRIVALS_PER_DAY, PEER_MIN, bp_per_won

#: 무리 잔존칸 — `kbond_view.BUCKETS` 와 같은 값. (한 화면이 두 축을 말하면 안 된다.)
PEER_EDGES = [0, 1, 2, 3, 5, 10, 99]
PEER_LABELS = ["~1년", "1~2", "2~3", "3~5", "5~10", "10년+"]

#: 「~1년」 칸 **안**을 다시 가르는 눈금. 이 칸에서만 묻는다 — 문제가 여기 있다.
FINE_EDGES = [0, 0.02, 0.05, 0.1, 0.25, 0.5, 1.0]
FINE_LABELS = ["0~0.02", "0.02~0.05", "0.05~0.1", "0.1~0.25", "0.25~0.5", "0.5~1"]


def bp_per_won_vec(ttm):
    """`alarm_sizing.bp_per_won` 을 벡터로. **식은 거기 하나뿐**이다."""
    return np.array([bp_per_won(float(t)) if t is not None else np.nan for t in ttm],
                    dtype=float)


def load() -> pd.DataFrame:
    df = pq.read_table(PARQUET, columns=[
        "Date", "Position", "Sector", "AtMP", "TTM_years", "QuoteVsMP_bp",
        "QuoteMethod", "IsInquiry"]).to_pandas()
    d = df[(df.Position == "SELL") & (~df.AtMP.fillna(False))
           & (~df.IsInquiry.fillna(False)) & df.QuoteVsMP_bp.notna()
           & df.TTM_years.notna() & (df.TTM_years > 0)
           & (df.Sector == "크레딧/기타")].copy()
    d["pb"] = pd.cut(d.TTM_years, PEER_EDGES, labels=PEER_LABELS, right=False)
    g = d.groupby(["Date", "pb"], observed=True).QuoteVsMP_bp
    d["n_peer"] = g.transform("size")
    d = d[d.n_peer >= PEER_MIN].copy()
    d["dev"] = d.QuoteVsMP_bp - d.groupby(
        ["Date", "pb"], observed=True).QuoteVsMP_bp.transform("median")
    d["won"] = d.dev / bp_per_won_vec(d.TTM_years.to_numpy())   # 단가 원(액면 1만원)
    return d


def main() -> int:
    d = load()
    print(f"크레딧 SELL 값부른 오퍼 {len(d):,}건 · "
          f"{d.Date.min().date()}~{d.Date.max().date()} · 근사 무리 n>={PEER_MIN}")
    print(f"무리 중앙 대비 편차 전체 중앙 {d.dev.median():+.2f}bp\n")

    one = d[d.pb == "~1년"].copy()
    one["fb"] = pd.cut(one.TTM_years, FINE_EDGES, labels=FINE_LABELS, right=False)
    base = (one.dev >= 3).mean()
    print("【A】 «~1년» 한 무리 안에서, 잔존을 다시 갈라 본 «무리 중앙 대비» 편차")
    print("     (같은 무리다 — 잔존 사흘짜리와 열한 달짜리가 같은 중앙과 비교된다)")
    print(f"{'잔존(년)':>10s} {'n':>8s} {'p50':>8s} {'p90':>8s} {'p99':>9s} {'IQR':>7s}"
          f" {'>=+3bp':>7s} {'울림배율':>8s}")
    for lab in FINE_LABELS:
        s = one[one.fb == lab]
        if len(s) < 30:
            continue
        q = np.percentile(s.dev, [25, 50, 75, 90, 99])
        print(f"{lab:>10s} {len(s):8,d} {q[1]:+8.2f} {q[3]:+8.2f} {q[4]:+9.2f}"
              f" {q[2]-q[0]:7.2f} {(s.dev>=3).mean():6.1%} {(s.dev>=3).mean()/base:7.2f}x")
    print(f"     무리 전체 >=+3bp {base:.1%} · ★IQR 이 4.6배, p99 가 15배 벌어진다\n")

    print("【B】 자가 어디서 늘어나나 — 짧은 잔존 견적의 표기")
    sub = d[d.TTM_years < 0.1]
    vc = sub.QuoteMethod.value_counts(normalize=True)
    print(f"     잔존<0.1년 {len(sub):,}건 중 "
          + " · ".join(f"{k} {v:.1%}" for k, v in vc.head(3).items()))
    print("     `spread_won` 은 원 단위다 — `won_to_bp` 가 표 밖(<0.125년)에서 **1/잔존**을")
    print("     곱하므로 잔존 0.014년이면 **끝전 1원이 71bp** 가 된다.\n")

    print("【C】 그래서 «3bp» 는 잔존마다 돈이 얼마인가 (환산은 실측표)")
    print(f"{'잔존(년)':>10s} {'bp/원':>8s} {'3bp = 단가':>12s} {'100억에':>16s}")
    for t in (0.01, 0.05, 0.125, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0):
        r = float(bp_per_won(t))
        print(f"{t:10.2f} {r:8.2f} {3/r:11.3f}원 {3/r*1e6:15,.0f}원")
    print("     ★같은 «3bp» 가 잔존 0.01년과 1년 사이에서 **100배** 차이다.\n")

    print("【D】 지금 규칙(dev>=3bp)이 울리는 것의 단가 분포")
    h = d[d.dev >= 3]
    for c in (0.5, 1, 2, 3, 5):
        print(f"     단가 < {c:>3}원 : {(h.won<c).mean():6.1%}  (100억에 {c*1e6:>12,.0f}원 미만)")
    print()

    print(f"【E】 후보 규칙 — 하루 환산 = 도착 {ARRIVALS_PER_DAY}건 × 비율")
    rules = {
        "지금        dev>=3bp": d.dev >= 3,
        "하한 0.05년 + dev>=3bp": (d.dev >= 3) & (d.TTM_years >= 0.05),
        "하한 0.25년 + dev>=3bp": (d.dev >= 3) & (d.TTM_years >= 0.25),
        "돈문턱      dev>=3bp & 단가>=1원": (d.dev >= 3) & (d.won >= 1),
        "돈문턱      dev>=3bp & 단가>=2원": (d.dev >= 3) & (d.won >= 2),
        "돈문턱      dev>=3bp & 단가>=3원": (d.dev >= 3) & (d.won >= 3),
        "돈만        단가>=3원": d.won >= 3,
    }
    print(f"{'규칙':<32s} {'비율':>7s} {'하루':>7s} {'<0.1년':>7s} {'<0.25년':>8s}"
          f" {'중앙dev':>8s} {'중앙잔존':>8s} {'중앙단가':>9s}")
    for k, m in rules.items():
        s = d[m]
        print(f"{k:<32s} {m.mean():6.2%} {m.mean()*ARRIVALS_PER_DAY:6.1f}건"
              f" {(s.TTM_years<0.1).mean():6.1%} {(s.TTM_years<0.25).mean():7.1%}"
              f" {s.dev.median():+7.2f} {s.TTM_years.median():7.2f} {s.won.median():7.2f}원")
    print("\n⚠하루 환산은 **자릿수만** 본다 — 비율은 원장 전체 풀에서 잰 것이고 도착 38건은")
    print("  원장 역사의 중앙이라 축이 정확히 같지 않다(`alarm_sizing` 독스트링과 같은 주의).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
