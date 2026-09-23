"""v2 — 두 가지를 고친다.
  (a) 한쪽 호가는 mid 가 아니다.  오퍼만 = mid - 반스프레드, 비드만 = mid + 반스프레드.
      책은 한 틱(0.5bp)이라 반스프레드 0.25bp 로 보정한다 (09-15 실측).
  (b) 목표를 잔차로 바꾼다.  y = curve(ttm) + e  ->  ML 은 e 만 배운다.
      커브는 그날 호가를 ttm 에 국소선형 적합(자기 자신 제외).
"""
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HALF = 0.25   # bp, 반스프레드


def mid_est(df):
    m = df["mid"].copy()
    only_off = df.off_last.notna() & df.bid_last.isna()
    only_bid = df.bid_last.notna() & df.off_last.isna()
    m[only_off] = df.off_last[only_off] + HALF
    m[only_bid] = df.bid_last[only_bid] - HALF
    return m


def loo_local_linear(d, x, v, w, bw=1.2):
    """그날 안에서, 자기 자신을 뺀 국소선형 적합값을 각 점에서 돌려준다."""
    out = np.full(len(x), np.nan)
    nn = np.zeros(len(x))
    for day in np.unique(d):
        p = np.where(d == day)[0]
        xi, vi, wi = x[p], v[p], w[p]
        ok = ~np.isnan(vi) & ~np.isnan(xi)
        for j in range(len(p)):
            K = np.exp(-((xi - xi[j]) / bw) ** 2) * wi
            K[j] = 0.0
            K[~ok] = 0.0
            s = K.sum()
            if s < 0.3:
                continue
            nn[p[j]] = (K > 0.05).sum()
            dx = xi - xi[j]
            S0, S1, S2 = K.sum(), (K * dx).sum(), (K * dx * dx).sum()
            T0, T1 = (K * np.nan_to_num(vi)).sum(), (K * dx * np.nan_to_num(vi)).sum()
            det = S0 * S2 - S1 * S1
            out[p[j]] = (S2 * T0 - S1 * T1) / det if abs(det) > 1e-9 else T0 / S0
    return out, nn


FEATS = ["ttm", "q_n", "q_first", "q_last", "q_lo", "q_hi", "q_std", "q_tlast", "q_tfirst",
         "off_last", "off_n", "off_t", "bid_last", "bid_n", "bid_t", "m_est", "both", "qspread",
         "cvfit", "cvn", "cv_b", "cv_s", "cv_l", "dmp_prev", "res_prev", "dev"]


def prep(cut):
    df = pd.read_parquet(f"panel_{cut}.parquet").sort_values(["d", "ttm"]).reset_index(drop=True)
    df["m_est"] = mid_est(df)
    # 신뢰 가중: 양면 > 한쪽, 최근 호가일수록
    df["w"] = np.where(df.both == 1, 1.0, 0.45) * (0.5 + 0.5 * df.q_tlast / 480.0)
    fit, nn = loo_local_linear(df.d.values, df.ttm.values.astype(float),
                               df.m_est.values.astype(float), df.w.values.astype(float))
    df["cvfit"], df["cvn"] = fit, nn
    df["dev"] = df.m_est - df.cvfit          # 이 종목이 커브에서 벗어난 폭
    return df


def sc(nm, yh, y):
    e = np.abs(yh - y)
    return f"{nm:30s} median {np.median(e):5.2f}  MAE {e.mean():5.2f}  RMSE {np.sqrt(((yh-y)**2).mean()):5.2f}  R2 {1-((yh-y)**2).sum()/(y**2).sum():6.3f}"


for cut in ["1100", "1300", "1500", "1530"]:
    df = prep(cut)
    print(f"\n===== cutoff {cut[:2]}:{cut[2:]}   curve fitted on {df.cvfit.notna().mean():.0%} of rows =====")
    for a, b in (("2025-07-01", "2025-12-31"), ("2026-01-01", "2026-09-30")):
        tr = df[(df.d < a) & df.cvfit.notna()].copy()
        te = df[(df.d >= a) & (df.d <= b) & df.cvfit.notna()].copy()
        if not len(te):
            continue
        tr["e"] = tr.y - tr.cvfit
        m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.04, max_depth=4,
                                          min_samples_leaf=60, l2_regularization=2.0,
                                          random_state=0)
        m.fit(tr[FEATS], tr.e)
        y = te.y.to_numpy()
        print(f"  test {a[:7]}~{b[:7]}  n={len(te):,}  train={len(tr):,}   |y| median {np.median(np.abs(y)):.2f}bp")
        print("     " + sc("(0) yesterday MP", np.zeros(len(te)), y))
        print("     " + sc("(1) bucket-median rule", te.rule.to_numpy() if "rule" in te else np.zeros(len(te)), y))
        print("     " + sc("(2) curve fit (no ML)", te.cvfit.to_numpy(), y))
        print("     " + sc("(3) curve fit + ML residual", te.cvfit.to_numpy() + m.predict(te[FEATS]), y))
