"""민평이 맞나 우리 책이 맞나 — 체결을 과녁으로 마크를 채점한다. [2026-09-15]

[OWNER 2026-09-15] 레인 방향 = «알파 소스가 아니라 데스크의 값 진실 층»(§1). 그 방향이
서려면 먼저 이게 참이어야 한다: **우리 책의 mid 가 관행 마크(민평)보다 «거래가 나는 자리»
를 잘 말한다.** 아니면 화면은 «지금» 을 말할 뿐 «값» 은 아니고, 방향을 접어야 한다.

## 과녁과 경쟁자

과녁 = 체결 금리(국고, 문면에 종목·레벨이 있는 것). 같은 순간에 각 마크가 얼마나 틀렸나.

| 경쟁자 | 그 시각에 실제로 손에 있는가 |
|---|---|
| `mid_h` 우리 책 mid, 체결 **h 분 전** 기준 | 있다 |
| `민평_전일` 전 영업일 민평 | 있다 (라이브 엔진이 쓰는 바로 그 값) |
| `직전체결` 같은 종목 그날 직전 체결 | 있다 (있을 때만) |
| `민평_당일` 그날 종가 민평 | **없다 — 선견이다.** 상한 참고로만 |
| `민평_전일+커브이동` 전일 민평에 그날 **그 연물 지표물**의 우리-책 이동을 더한 것 | 있다 |

★**«민평_전일» 만 이기는 건 시시하다.** 그건 「오늘이 어제보다 오늘에 가깝나」라서 뻔하다.
진짜 물음은 **«그 종목 호가가 커브 이동 너머로 무엇을 더 아는가»** 다. 그래서 지표물 이동을
전일 민평에 얹은 상대를 따로 둔다. 이걸 못 이기면 우리 책은 «빠른 커브» 일 뿐이고, 이기면
종목 고유 정보가 있다는 뜻이라 RV 가 기댈 수 있다. (지표물 자신은 이 비교에서 뺀다 — 순환이다.)

★**민평은 종가 평가다**(`국고통_민평` 의 최대 일자가 늘 전 영업일이고, 라이브 `mp_date` 도
전일이다). 그래서 본표의 `MPYieldDB`·`QuoteVsMP_bp` 는 **같은 날 종가에 붙은 값**이라
장중 예측 문맥에서는 선견이다. 서술(그날 평가 대비 어디였나)에는 맞고 예측에는 못 쓴다.

## 왜 h 를 두나 — 이 검정의 급소

h=0 은 **기울어져 있다.** 체결의 81%가 최우선 «레벨» 에서 나고 책은 한 틱이라
`|체결 − mid|` 가 구성상 0.25bp 로 나온다. 마크가 좋아서가 아니라 과녁이 책 안에 있어서다.
(09-15 에 같은 병으로 부호가 뒤집힌 전례 — 귀속 규칙과 설명 변수가 축을 공유하면 검정이 아니다.)
그래서 **h=15·60분** 이 본판이다. 그때 mid 는 체결보다 앞선 정보만 쓴다.
h=0 도 같이 찍되 «기울어진 칸» 이라고 이름을 달아 둔다.

  python kbond_mark_test.py [--since 2024-02-14] [--out ...json]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from kbond_dyn_study import secs, uncross, best_of, TTL, BASE    # noqa: E402

HS = [0, 900, 3600]          # 체결 몇 초 «전» 의 책을 쓸 것인가
FILL_WIN = 1800


def load_mp_panel(d0, d1):
    """(Date, BondCode) -> 민평 일별 패널. enrich 와 같은 매핑을 쓴다(같은 축은 같은 함수)."""
    from enrich_kbond_quotes import load_mp
    return load_mp(pd.Series([pd.Timestamp(d0), pd.Timestamp(d1)]))


def load_mats():
    """BondCode -> 만기일. 연물 버킷을 내려고 국채_발행정보에서 직접 받는다."""
    from sqlalchemy import text
    from kbond_live import engine
    with engine().connect() as c:
        iss = pd.read_sql(text(
            "SELECT 종목명 AS BondCode, 만기일 FROM `국채_발행정보` "
            "WHERE 종목명 REGEXP '^[0-9]{1,2}-[0-9]{1,2}$'"), c)
    iss["BondCode"] = iss.BondCode.str.replace(r"^(\d{2})-0*(\d+)$", r"\1-\2", regex=True)
    return iss.drop_duplicates("BondCode").set_index("BondCode")["만기일"]


def agg(e):
    e = np.abs(np.asarray(e, float))
    e = e[~np.isnan(e)]
    if not len(e):
        return None
    return {"n": int(len(e)), "med": float(np.median(e)), "mean": float(e.mean()),
            "p90": float(np.percentile(e, 90))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2024-02-14")
    ap.add_argument("--out", default=BASE + r"\kbond_mark_test.json")
    a = ap.parse_args()
    t0 = time.time()

    q = pd.read_parquet(BASE + r"\kbond_structured_data.parquet",
                        columns=["Date", "Timestamp", "BondCode", "MsgType", "Position",
                                 "QuoteYield", "BrokerKey", "Message"],
                        filters=[("Sector", "==", "국고")])
    q = q[(q.MsgType == "QUOTE") & q.BondCode.notna() & q.Position.isin(["BUY", "SELL"])
          & q.QuoteYield.notna() & q.BrokerKey.notna() & (q.Date >= a.since)].copy()
    q["ts"] = secs(q.Timestamp)
    q["b20"] = (q.ts // 20).astype(int)
    q = q.sort_values("ts").drop_duplicates(["BrokerKey", "Message", "b20"], keep="first")
    q["bk"] = q.BrokerKey.map(lambda s: str(s)[:14])

    f = pd.read_parquet(BASE + r"\kbond_fills.parquet")
    f = f[(f.Sector == "국고") & f.BondCode.notna() & f.QuoteYield.notna()
          & (f.RepostSeq.fillna(0) == 0) & (f.DupSeq.fillna(0) == 0)
          & (f.Date >= a.since)].copy()
    f["ts"] = secs(f.Timestamp)
    assert 8 * 3600 < np.median(f.ts - secs(f.Date)) < 20 * 3600, "체결 시각이 장중이 아니다"

    mp = load_mp_panel(q.Date.min() - pd.Timedelta(days=10), q.Date.max())
    mats = load_mats()
    print(f"적재 {time.time()-t0:.0f}s — 호가 {len(q):,} · 체결 {len(f):,} · "
          f"민평 패널 {len(mp):,}행 {mp.Date.nunique()}일 · 만기 {len(mats):,}종")

    # 전일 민평: 같은 종목의 «그 날짜보다 앞선 마지막» 민평. merge_asof(allow_exact_matches=False)
    mp = mp.sort_values("Date")
    fk = f[["Date", "BondCode"]].copy().sort_values("Date")
    prev = pd.merge_asof(fk.reset_index(), mp.sort_values("Date"), on="Date", by="BondCode",
                         allow_exact_matches=False, direction="backward")
    same = pd.merge_asof(fk.reset_index(), mp.sort_values("Date"), on="Date", by="BondCode",
                         allow_exact_matches=True, direction="backward")
    f["mp_prev"] = prev.set_index("index").MPYieldDB
    f["mp_same"] = same.set_index("index").MPYieldDB
    # 같은 날 민평이 실제로 그날 것인지 확인 (아니면 전일과 같은 값이 들어온다)
    f["mp_same_isday"] = same.set_index("index").Date.eq(f.Date)
    print(f"  민평 전일 {f.mp_prev.notna().mean():.1%} · 당일 {(f.mp_same.notna() & f.mp_same_isday).mean():.1%}")

    # ── 책을 접으며 각 체결에 mid_h 와 직전 체결을 붙인다 ─────────────────────
    q = q.sort_values(["Date", "BondCode", "ts"])
    f = f.sort_values(["Date", "BondCode", "ts"])
    fg = {k: g for k, g in f.groupby(["Date", "BondCode"], sort=False)}
    out = {h: {} for h in HS}
    prevfill = {}
    prevgap = {}
    nqs = {}
    mids = {}          # (date, code) -> (t배열, mid배열) · 커브이동 상대가 쓴다
    nq_day = {}        # (date, code) -> 호가 수 · 지표물을 «그날 가장 많이 불린 종목» 으로 고른다
    for (date, code), g in q.groupby(["Date", "BondCode"], sort=False):
        fl = fg.get((date, code))
        if fl is None:
            continue
        ev = [(t, 0, i) for i, t in enumerate(g.ts.to_numpy())]
        ev += [(t, 1, i) for i, t in enumerate(fl.ts.to_numpy())]
        ev.sort()
        book = {}
        mt, mv = [], []          # mid 시계열
        gb, gs, gy = g.bk.to_numpy(), g.Position.to_numpy(), g.QuoteYield.to_numpy(float)
        fy, fidx = fl.QuoteYield.to_numpy(float), fl.index.to_numpy()
        last_fill = None
        for t, kind, i in ev:
            if kind == 0:
                book[(gb[i], "S" if gs[i] == "SELL" else "B")] = {
                    "t": t, "s": "S" if gs[i] == "SELL" else "B", "y": float(gy[i]), "k": gb[i]}
                alive = [e for e in book.values() if t - e["t"] <= TTL]
                asks, bids = uncross([e for e in alive if e["s"] == "S"],
                                     [e for e in alive if e["s"] == "B"])
                fa, fb = best_of(asks, bids)
                if fa is not None and fb is not None:
                    mt.append(t)
                    mv.append((fa["y"] + fb["y"]) / 2)
                continue
            ix = int(fidx[i])
            arr = np.asarray(mt)
            for h in HS:
                j = np.searchsorted(arr, t - h, side="right") - 1
                # 너무 묵은 mid 는 «그 시각의 마크» 가 아니다 — TTL 밖이면 없는 것으로 본다
                if j >= 0 and (t - h) - arr[j] <= TTL:
                    out[h][ix] = mv[j]
            if last_fill is not None and t - last_fill[0] <= FILL_WIN:
                prevfill[ix] = last_fill[1]
                prevgap[ix] = t - last_fill[0]
            nqs[ix] = len(mt)
            last_fill = (t, float(fy[i]))
        mids[(date, code)] = (np.asarray(mt), np.asarray(mv))
        nq_day[(date, code)] = len(g)
    for h in HS:
        f[f"mid_{h}"] = pd.Series(out[h])
    f["pf"] = pd.Series(prevfill)
    f["pfgap"] = pd.Series(prevgap)
    print(f"접기 {time.time()-t0:.0f}s")

    # ── 채점 ─────────────────────────────────────────────────────────────────
    y = f.QuoteYield
    E = pd.DataFrame({
        "민평_전일": (y - f.mp_prev) * 100,
        "민평_당일(선견)": (y - f.mp_same.where(f.mp_same_isday)) * 100,
        "직전체결": (y - f.pf) * 100,
        **{f"우리 mid −{h//60}분" + ("(기울어짐)" if h == 0 else ""): (y - f[f"mid_{h}"]) * 100
           for h in HS},
    })
    R = {"n_fills": int(len(f)), "since": a.since,
         "coverage": {c: float(E[c].notna().mean() * 100) for c in E.columns},
         "all": {c: agg(E[c]) for c in E.columns}}
    print(f"\n체결 {len(f):,}건 · 커버리지(%) " +
          " · ".join(f"{c} {v:.0f}" for c, v in R["coverage"].items()))
    print("\n[전체] |체결 − 마크| bp")
    for c in E.columns:
        s = R["all"][c]
        print(f"   {c:>22} n={s['n']:>6,} 중앙 {s['med']:5.2f} 평균 {s['mean']:6.2f} p90 {s['p90']:6.2f}")

    # 짝 비교 — 둘 다 있는 체결에서만. 이게 본판이다.
    R["paired"] = {}
    print("\n[짝 비교] 민평_전일 대 우리 mid — 둘 다 있는 체결만")
    for h in HS:
        col = f"우리 mid −{h//60}분" + ("(기울어짐)" if h == 0 else "")
        m = E["민평_전일"].notna() & E[col].notna()
        a_, b_ = E.loc[m, "민평_전일"].abs(), E.loc[m, col].abs()
        win = float((b_ < a_ - 1e-9).mean() * 100)
        tie = float((np.abs(b_ - a_) <= 1e-9).mean() * 100)
        R["paired"][col] = {"n": int(m.sum()), "mp_med": float(a_.median()),
                            "ours_med": float(b_.median()), "win_pct": win, "tie_pct": tie,
                            "mp_mean": float(a_.mean()), "ours_mean": float(b_.mean())}
        s = R["paired"][col]
        print(f"   {col:>22} n={s['n']:>6,} · 민평 {s['mp_med']:.2f} 대 우리 {s['ours_med']:.2f} (중앙)"
              f" · 평균 {s['mp_mean']:.2f} 대 {s['ours_mean']:.2f} · 우리가 이김 {win:.1f}% (동률 {tie:.1f}%)")

    # 연물 버킷 · 시간대
    ttm = ((f.BondCode.map(mats) - f.Date).dt.days / 365.25)
    f["ten"] = pd.cut(ttm, [0, 1.5, 2.5, 4, 7, 12, 25, 60],
                      labels=["~1.5y", "2y", "3y", "5y", "10y", "20y", "30y+"])
    col15 = "우리 mid −15분"
    R["by_tenor"] = {}
    print("\n[연물별] 중앙 |오차| bp — 민평_전일 대 우리 mid −15분 (둘 다 있는 체결)")
    for k, ix in f.groupby("ten", observed=True).groups.items():
        m = E.loc[ix, "민평_전일"].notna() & E.loc[ix, col15].notna()
        if m.sum() < 50:
            continue
        a_, b_ = E.loc[ix, "민평_전일"][m].abs(), E.loc[ix, col15][m].abs()
        R["by_tenor"][str(k)] = {"n": int(m.sum()), "mp": float(a_.median()),
                                 "ours": float(b_.median()),
                                 "win": float((b_ < a_ - 1e-9).mean() * 100)}
        v = R["by_tenor"][str(k)]
        print(f"   {str(k):>6} n={v['n']:>6,} · 민평 {v['mp']:5.2f} · 우리 {v['ours']:5.2f}"
              f" · 우리가 이김 {v['win']:.0f}%")

    f["hr"] = ((f.ts - secs(f.Date)) // 3600).astype(int)
    R["by_hour"] = {}
    print("\n[시간대별] 중앙 |오차| bp (같은 짝)")
    for k, ix in f.groupby("hr").groups.items():
        if not (8 <= k <= 16):
            continue
        m = E.loc[ix, "민평_전일"].notna() & E.loc[ix, col15].notna()
        if m.sum() < 50:
            continue
        a_, b_ = E.loc[ix, "민평_전일"][m].abs(), E.loc[ix, col15][m].abs()
        R["by_hour"][int(k)] = {"n": int(m.sum()), "mp": float(a_.median()),
                                "ours": float(b_.median()),
                                "win": float((b_ < a_ - 1e-9).mean() * 100)}
        v = R["by_hour"][int(k)]
        print(f"   {k:>2}시 n={v['n']:>6,} · 민평 {v['mp']:5.2f} · 우리 {v['ours']:5.2f}"
              f" · 우리가 이김 {v['win']:.0f}%")

    # 종목-일 군집 — 날짜별 «우리가 이긴 비율» 의 분포(한 날이 끌고 가지 않았나)
    m = E["민평_전일"].notna() & E[col15].notna()
    dd = pd.DataFrame({"d": f.Date[m], "w": (E[col15][m].abs() < E["민평_전일"][m].abs() - 1e-9)})
    byday = dd.groupby("d").w.agg(["size", "mean"])
    byday = byday[byday["size"] >= 10]
    R["by_day"] = {"n_days": int(len(byday)), "win_med": float(byday["mean"].median() * 100),
                   "days_ours_wins": float((byday["mean"] > 0.5).mean() * 100)}
    print(f"\n[날짜별] 체결 10건 이상인 {len(byday):,}일 · 우리가 이긴 비율 중앙 "
          f"{R['by_day']['win_med']:.0f}% · **우리가 이긴 날 {R['by_day']['days_ours_wins']:.0f}%**")

    # ── 더 센 상대: 전일 민평 + 그날 «그 연물 지표물» 의 우리-책 이동 ──────────
    # 이걸 못 이기면 우리 책은 «빠른 커브» 일 뿐이다. 이기면 종목 고유 정보가 있다는 뜻이고,
    # 그때에만 RV 가 이 층에 기댈 수 있다. ★지표물 자신의 체결은 뺀다(순환).
    def ten_of(date, code):
        m = mats.get(code)
        if m is None or pd.isna(m):
            return None
        yrs = (m - date).days / 365.25
        for lo, hi, nm in [(0, 1.5, "~1.5y"), (1.5, 2.5, "2y"), (2.5, 4, "3y"), (4, 7, "5y"),
                           (7, 12, "10y"), (12, 25, "20y"), (25, 60, "30y+")]:
            if lo <= yrs < hi:
                return nm
        return None

    # (date, code) -> 전일 민평
    pairs = pd.DataFrame([(d, c) for (d, c) in nq_day], columns=["Date", "BondCode"]).sort_values("Date")
    pv = pd.merge_asof(pairs.reset_index(drop=True), mp.sort_values("Date"), on="Date",
                       by="BondCode", allow_exact_matches=False, direction="backward")
    mp_prev_map = {(d, c): v for d, c, v in zip(pv.Date, pv.BondCode, pv.MPYieldDB) if pd.notna(v)}
    # (date, 연물) -> 그날 호가가 많은 순서의 종목 목록 = 지표물 후보
    bench = {}
    for (d, c), n in nq_day.items():
        tn = ten_of(d, c)
        if tn:
            bench.setdefault((d, tn), []).append((n, c))
    for k in bench:
        bench[k].sort(reverse=True)

    H2 = 900
    shift_err, own_err, keys = [], [], []
    for ix, row in f[["Date", "BondCode", "QuoteYield", "ts", "mp_prev", f"mid_{H2}"]].iterrows():
        d, c = row.Date, row.BondCode
        tn = ten_of(d, c)
        if tn is None or pd.isna(row.mp_prev) or pd.isna(row[f"mid_{H2}"]):
            continue
        cand = [cc for _, cc in bench.get((d, tn), []) if cc != c]
        if not cand:
            continue
        bc = cand[0]
        bmp = mp_prev_map.get((d, bc))
        bt, bv = mids.get((d, bc), (None, None))
        if bmp is None or bt is None or not len(bt):
            continue
        j = np.searchsorted(bt, row.ts - H2, side="right") - 1
        if j < 0 or (row.ts - H2) - bt[j] > TTL:
            continue
        shift = bv[j] - bmp                       # 그날 그 연물이 얼마나 움직였나
        shift_err.append((row.QuoteYield - (row.mp_prev + shift)) * 100)
        own_err.append((row.QuoteYield - row[f"mid_{H2}"]) * 100)
        keys.append(ix)
    se, oe = np.abs(np.asarray(shift_err)), np.abs(np.asarray(own_err))
    R["curve_shift"] = {
        "n": int(len(se)), "h_min": H2 // 60,
        "shift_med": float(np.median(se)), "shift_mean": float(se.mean()),
        "ours_med": float(np.median(oe)), "ours_mean": float(oe.mean()),
        "win_pct": float((oe < se - 1e-9).mean() * 100),
        "tie_pct": float((np.abs(oe - se) <= 1e-9).mean() * 100),
    }
    v = R["curve_shift"]
    print(f"\n[더 센 상대] 전일 민평 + 그날 지표물 이동  대  우리 mid −{v['h_min']}분 · n={v['n']:,}")
    print(f"   커브이동 중앙 {v['shift_med']:.2f} 평균 {v['shift_mean']:.2f}  대  "
          f"우리 중앙 {v['ours_med']:.2f} 평균 {v['ours_mean']:.2f}"
          f"  ·  우리가 이김 {v['win_pct']:.1f}% (동률 {v['tie_pct']:.1f}%)")

    # 직전 체결이 «같은 거래의 재보고» 는 아닌가 — 시차를 본다
    pg = f.pfgap.dropna()
    R["prevfill_gap"] = {"n": int(len(pg)), "med_s": float(pg.median()),
                         "under_60s_pct": float((pg <= 60).mean() * 100)}
    print(f"   (직전체결 상대: 시차 중앙 {R['prevfill_gap']['med_s']:.0f}초 · "
          f"60초 이내 {R['prevfill_gap']['under_60s_pct']:.0f}% — 같은 거래의 재보고가 섞였다는 뜻)")

    R["elapsed_s"] = time.time() - t0
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(R, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n저장 {a.out} · {R['elapsed_s']:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
