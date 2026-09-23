"""Panel for: yesterday's MP + today's quotes up to time t  ->  today's closing MP.

Strict as-of discipline
    label    y = (MP_close(D,i) - MP_close(D-1,i)) * 100   [bp]
    features use ONLY quotes with Time < cutoff on day D, and MP up to D-1.
Writes one parquet per cutoff.
"""
import os, sys, numpy as np, pandas as pd
from sqlalchemy import create_engine, text

PARQ = r"C:\Users\infomax\Projects\data\kbond\kbond_structured_data.parquet"
OUT = os.path.dirname(os.path.abspath(__file__))
CUTS = ["11:00:00", "13:00:00", "15:00:00", "15:30:00"]


def eng():
    u, p = os.environ["BW_MYSQL_USER"], os.environ["BW_MYSQL_PASSWORD"]
    h, q = os.environ["BW_MYSQL_HOST"], os.environ["BW_MYSQL_PORT"]
    return create_engine(f"mysql+pymysql://{u}:{p}@{h}:{q}/infomax?charset=utf8mb4")


def norm(s):
    return s.str.replace(r'^(\d{2})-0*(\d+)$', r'\1-\2', regex=True)


def load_mp():
    with eng().connect() as c:
        mp = pd.read_sql(text("SELECT 일자 d, 종목코드 k, 민평 y FROM `국고통_민평` "
                              "WHERE 일자>='2023-11-01' AND LEFT(종목코드,4)='KR10'"), c)
        iss = pd.read_sql(text("SELECT 표준코드 k, 종목명 c, 만기일 m FROM `국채_발행정보` "
                               "WHERE 종목명 REGEXP '^[0-9]{1,2}-[0-9]{1,2}$'"), c)
    iss["c"] = norm(iss.c)
    mp = mp.merge(iss.drop_duplicates("k")[["k", "c"]], on="k")
    piv = mp.pivot_table(index="d", columns="c", values="y").sort_index()
    return piv, dict(zip(iss.c, pd.to_datetime(iss.m)))


def load_quotes():
    cols = ["Date", "Time", "Sector", "BondCode", "Position", "QuoteYield", "MsgType", "AmountEff"]
    df = pd.read_parquet(PARQ, columns=cols)
    g = df[(df.Sector == "국고") & df.BondCode.notna() & df.QuoteYield.notna()
           & df.MsgType.eq("QUOTE") & df.Position.isin(["SELL", "BUY"])].copy()
    g["c"] = norm(g.BondCode)
    g["d"] = pd.to_datetime(g.Date)
    g["mins"] = (pd.to_timedelta(g.Time).dt.total_seconds() / 60 - 540).clip(0, 480)
    return g[["d", "c", "Time", "mins", "Position", "QuoteYield", "AmountEff"]]


def own_features(s, yest):
    """s: quotes of one cutoff, already filtered.  yest: Series indexed (d,c) -> MP(D-1)."""
    s = s.join(yest.rename("yest"), on=["d", "c"]).dropna(subset=["yest"])
    s["bp"] = (s.QuoteYield - s.yest) * 100
    s = s[s.bp.abs() < 100]                       # 파싱 잔재 방어
    s = s.sort_values(["d", "c", "Time"])
    gb = s.groupby(["d", "c"])
    f = pd.DataFrame({
        "q_n": gb.size(),
        "q_first": gb.bp.first(),
        "q_last": gb.bp.last(),
        "q_lo": gb.bp.min(),
        "q_hi": gb.bp.max(),
        "q_std": gb.bp.std(),
        "q_tlast": gb.mins.max(),
        "q_tfirst": gb.mins.min(),
    })
    for side, tag in (("SELL", "off"), ("BUY", "bid")):
        t = s[s.Position == side].groupby(["d", "c"])
        f[f"{tag}_last"] = t.bp.last()
        f[f"{tag}_n"] = t.size()
        f[f"{tag}_t"] = t.mins.max()
    f["mid"] = f[["off_last", "bid_last"]].mean(axis=1)
    f["both"] = f[["off_last", "bid_last"]].notna().all(axis=1).astype(int)
    f["qspread"] = f.bid_last - f.off_last
    return f


def curve_features(f, ttm):
    """leave-one-out kernel averages of other bonds' mid move, same day."""
    f = f.copy()
    f["ttm"] = ttm
    out = {}
    for w, tag in ((0.75, "n"), (2.5, "b")):
        num = np.zeros(len(f)); den = np.zeros(len(f)); cnt = np.zeros(len(f))
        idx = f.index.get_level_values(0)
        for d, blk in f.groupby(level=0):
            v = blk["mid"].to_numpy(); t = blk["ttm"].to_numpy()
            ok = ~np.isnan(v) & ~np.isnan(t)
            W = np.exp(-((t[:, None] - t[None, :]) / w) ** 2)
            W[:, ~ok] = 0.0
            np.fill_diagonal(W, 0.0)                       # leave-one-out
            pos = np.where(idx == d)[0]
            vv = np.nan_to_num(v)
            num[pos] = W @ vv
            den[pos] = W.sum(1)
            cnt[pos] = (W > 0.05).sum(1)
        out[f"cv_{tag}"] = np.where(den > 0, num / np.maximum(den, 1e-9), np.nan)
        out[f"cvn_{tag}"] = cnt
    for k, v in out.items():
        f[k] = v
    # short / long halves, leave-one-out
    for lo, hi, tag in ((0, 3, "s"), (3, 40, "l")):
        m = f.ttm.between(lo, hi)
        g = f[m].groupby(level=0)["mid"]
        ssum, scnt = g.transform("sum"), g.transform("count")
        loo = (ssum - f.loc[m, "mid"].fillna(0)) / (scnt - f.loc[m, "mid"].notna()).replace(0, np.nan)
        f[f"cv_{tag}"] = loo
    return f


def main():
    piv, mat = load_mp()
    prev = piv.shift(1)
    prev2 = piv.shift(2)
    yest = prev.stack().rename_axis(["d", "c"])
    today = piv.stack().rename_axis(["d", "c"])
    dprev = ((prev - prev2) * 100).stack().rename_axis(["d", "c"])
    q = load_quotes()
    print(f"quotes {len(q):,}  days {q.d.nunique()}  bonds {q.c.nunique()}")

    for cut in CUTS:
        f = own_features(q[q.Time < cut], yest)
        ttm = pd.Series({(d, c): (mat[c] - d).days / 365.25 if c in mat else np.nan
                         for d, c in f.index})
        f = curve_features(f, ttm)
        f["yest"] = yest.reindex(f.index)
        f["y"] = ((today.reindex(f.index) - f.yest) * 100)
        f["dmp_prev"] = dprev.reindex(f.index)
        f = f[f.y.notna() & f.ttm.between(0.05, 31)].copy()
        # 어제 「책이 알고 민평이 아직 안 넣은 것」
        r = f.reset_index()
        r["res_prev"] = np.nan
        key = r.set_index(["c", "d"]).index
        prev_res = (r.assign(res=r["mid"] - r["y"]).set_index(["c", "d"])["res"])
        r["d_lag"] = r.groupby("c")["d"].shift(1)
        lk = pd.MultiIndex.from_arrays([r["c"], r["d_lag"]])
        r["res_prev"] = prev_res.reindex(lk).to_numpy()
        r["gap_days"] = (r["d"] - r["d_lag"]).dt.days
        r.loc[r.gap_days > 4, "res_prev"] = np.nan
        p = os.path.join(OUT, f"panel_{cut[:2]}{cut[3:5]}.parquet")
        r.drop(columns=["d_lag"]).to_parquet(p, index=False)
        print(f"  {cut}  rows {len(r):,}  bonds {r.c.nunique()}  days {r.d.nunique()}  "
              f"two-sided {r.both.mean():.1%}  -> {os.path.basename(p)}")


if __name__ == "__main__":
    main()
