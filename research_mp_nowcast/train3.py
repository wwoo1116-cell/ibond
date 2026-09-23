"""v3 — 두 가지를 더 고친다.
  (c) 커브를 로버스트로: 커널가중 '중앙값' (평균은 이상호가에 끌린다 — v2 의 패인)
  (d) 빠진 입력: 장내 체결 테이프(`국채_체결금리`, 2024-02~2025-12).
      평가사가 실제로 보는 건 호가만이 아니다.
"""
import os, numpy as np, pandas as pd
from sqlalchemy import create_engine, text
from sklearn.ensemble import HistGradientBoostingRegressor

HALF = 0.25


def eng():
    u, p = os.environ["BW_MYSQL_USER"], os.environ["BW_MYSQL_PASSWORD"]
    h, q = os.environ["BW_MYSQL_HOST"], os.environ["BW_MYSQL_PORT"]
    return create_engine(f"mysql+pymysql://{u}:{p}@{h}:{q}/infomax?charset=utf8mb4")


def wmedian(v, w):
    o = np.argsort(v); v, w = v[o], w[o]
    c = np.cumsum(w)
    if c[-1] <= 0:
        return np.nan
    return v[np.searchsorted(c, c[-1] / 2.0)]


def loo_wmedian_curve(d, x, v, w, bw=1.0):
    out = np.full(len(x), np.nan); nn = np.zeros(len(x))
    for day in np.unique(d):
        p = np.where(d == day)[0]
        xi, vi, wi = x[p], v[p], w[p]
        ok = ~np.isnan(vi) & ~np.isnan(xi)
        for j in range(len(p)):
            K = np.exp(-((xi - xi[j]) / bw) ** 2) * wi
            K[j] = 0.0; K[~ok] = 0.0
            if K.sum() < 0.3:
                continue
            m = K > 1e-3
            out[p[j]] = wmedian(vi[m], K[m]); nn[p[j]] = m.sum()
    return out, nn


def mid_est(df):
    m = df["mid"].copy()
    a = df.off_last.notna() & df.bid_last.isna()
    b = df.bid_last.notna() & df.off_last.isna()
    m[a] = df.off_last[a] + HALF
    m[b] = df.bid_last[b] - HALF
    return m


def norm(s):
    return s.str.replace(r'^(\d{2})-0*(\d+)$', r'\1-\2', regex=True)


def load_trades(cut_frac):
    with eng().connect() as c:
        tr = pd.read_sql(text(
            "SELECT 일자 d, 시간 t, 표준코드 k, 매매수익률 y, 거래량 v FROM `국채_체결금리` "
            "WHERE 일자>='2024-02-01' AND LEFT(표준코드,4)='KR10' AND 매매수익률 IS NOT NULL"), c)
        iss = pd.read_sql(text("SELECT 표준코드 k, 종목명 c FROM `국채_발행정보` "
                               "WHERE 종목명 REGEXP '^[0-9]{1,2}-[0-9]{1,2}$'"), c)
    iss["c"] = norm(iss.c)
    tr = tr.merge(iss.drop_duplicates("k"), on="k")
    return tr[tr.t < cut_frac]


FEAT_Q = ["ttm", "q_n", "q_first", "q_last", "q_lo", "q_hi", "q_std", "q_tlast", "q_tfirst",
          "off_last", "off_n", "off_t", "bid_last", "bid_n", "bid_t", "m_est", "both", "qspread",
          "cvfit", "cvn", "dev", "dmp_prev", "res_prev"]
FEAT_T = ["tr_n", "tr_last", "tr_vwap", "tr_t", "tr_vol", "tcv", "tcvn", "tdev"]


def sc(nm, yh, y):
    e = np.abs(yh - y)
    return (f"{nm:34s} median {np.median(e):5.2f}  MAE {e.mean():5.2f}  "
            f"RMSE {np.sqrt(((yh-y)**2).mean()):5.2f}  R2 {1-((yh-y)**2).sum()/(y**2).sum():6.3f}")


def run(cut, use_trades):
    frac = int(cut[:2]) / 24 + int(cut[2:]) / 1440
    df = pd.read_parquet(f"panel_{cut}.parquet").sort_values(["d", "ttm"]).reset_index(drop=True)
    df["m_est"] = mid_est(df)
    df["w"] = np.where(df.both == 1, 1.0, 0.45) * (0.5 + 0.5 * df.q_tlast / 480.0)
    fit, nn = loo_wmedian_curve(df.d.values, df.ttm.values.astype(float),
                                df.m_est.values.astype(float), df.w.values.astype(float))
    df["cvfit"], df["cvn"] = fit, nn
    df["dev"] = df.m_est - df.cvfit
    feats = list(FEAT_Q)

    if use_trades:
        tr = load_trades(frac)
        tr = tr.merge(df[["d", "c", "yest"]], on=["d", "c"])
        tr["bp"] = (tr.y - tr.yest) * 100
        tr = tr[tr.bp.abs() < 100].sort_values(["d", "c", "t"])
        g = tr.groupby(["d", "c"])
        agg = pd.DataFrame({"tr_n": g.size(), "tr_last": g.bp.last(), "tr_t": g.t.max(),
                            "tr_vol": g.v.sum(),
                            "tr_vwap": g.apply(lambda x: np.average(x.bp, weights=np.maximum(x.v, 1)),
                                               include_groups=False)}).reset_index()
        df = df.merge(agg, on=["d", "c"], how="left")
        tfit, tnn = loo_wmedian_curve(df.d.values, df.ttm.values.astype(float),
                                      df.tr_vwap.values.astype(float),
                                      np.where(df.tr_n.notna(), 1.0, 0.0))
        df["tcv"], df["tcvn"] = tfit, tnn
        df["tdev"] = df.tr_vwap - df.tcv
        feats += FEAT_T
        df = df[df.d <= "2025-12-12"]

    lab = "quotes+trades" if use_trades else "quotes only"
    a, b = "2025-07-01", "2025-12-12"
    trn = df[(df.d < a) & df.cvfit.notna()].copy()
    te = df[(df.d >= a) & (df.d <= b) & df.cvfit.notna()].copy()
    trn["e"] = trn.y - trn.cvfit
    m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.04, max_depth=4,
                                      min_samples_leaf=60, l2_regularization=2.0, random_state=0)
    m.fit(trn[feats], trn.e)
    y = te.y.to_numpy()
    print(f"\n-- {cut[:2]}:{cut[2:]}  [{lab}]  test {a}~{b}  n={len(te):,}  train={len(trn):,}")
    print("   " + sc("(0) yesterday MP", np.zeros(len(te)), y))
    print("   " + sc("(1) bucket-median rule", te.rule.to_numpy(), y))
    print("   " + sc("(2) robust curve (no ML)", te.cvfit.to_numpy(), y))
    print("   " + sc("(3) robust curve + ML residual", te.cvfit.to_numpy() + m.predict(te[feats]), y))
    return m, te, feats


if __name__ == "__main__":
    for cut in ["1300", "1530"]:
        run(cut, False)
        run(cut, True)
