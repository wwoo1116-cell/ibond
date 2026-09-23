"""검정 수리 — 09-17.

앞서 보고한 t=2.36 은 단순 짝 t 였다. 포함관계(nested)에는 못 쓴다.
  포함 쌍   (커브)  vs  (커브 + ML 잔차)        -> Clark-West
  비포함 쌍 (구간중앙값 규칙) vs (커브+ML)       -> Diebold-Mariano + HLN
표본 단위는 종목일이 아니라 날짜다(같은 날 종목들이 함께 움직인다).
그래서 손실차를 날짜로 접고, 그 시계열에 Newey-West 를 건다.
"""
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from train3 import loo_wmedian_curve, mid_est, FEAT_Q


def nw_se(x, lag=None):
    x = np.asarray(x, float); T = len(x); m = x.mean(); u = x - m
    if lag is None:
        lag = int(np.floor(4 * (T / 100) ** (2 / 9)))
    g0 = (u @ u) / T
    s = g0
    for L in range(1, lag + 1):
        g = (u[L:] @ u[:-L]) / T
        s += 2 * (1 - L / (lag + 1)) * g
    return np.sqrt(max(s, 1e-18) / T), lag


def dm(e1, e2, day, loss="mse"):
    """H0: 같은 정확도.  d>0 이면 model2 가 낫다.  HLN 소표본 보정 + t_{T-1}."""
    L = (lambda e: e ** 2) if loss == "mse" else (lambda e: np.abs(e))
    d = pd.Series(L(e1) - L(e2)).groupby(day).mean()
    T = len(d)
    se, lag = nw_se(d.values)
    t = d.mean() / se
    h = 1
    hln = np.sqrt((T + 1 - 2 * h + h * (h - 1) / T) / T)
    from scipy import stats
    tc = t * hln
    p = 2 * (1 - stats.t.cdf(abs(tc), T - 1))
    return dict(stat=tc, p=p, T=T, lag=lag, mean=d.mean())


def cw(y, f1, f2, day):
    """Clark-West: 포함 쌍 전용.  f2 가 f1 을 품는다.  단측."""
    fh = (y - f1) ** 2 - ((y - f2) ** 2 - (f1 - f2) ** 2)
    d = pd.Series(fh).groupby(day).mean()
    T = len(d)
    se, lag = nw_se(d.values)
    t = d.mean() / se
    from scipy import stats
    return dict(stat=t, p=1 - stats.norm.cdf(t), T=T, lag=lag, mean=d.mean())


def build(cut):
    df = pd.read_parquet(f"panel_{cut}.parquet").sort_values(["d", "ttm"]).reset_index(drop=True)
    df["m_est"] = mid_est(df)
    df["w"] = np.where(df.both == 1, 1.0, 0.45) * (0.5 + 0.5 * df.q_tlast / 480.0)
    fit, nn = loo_wmedian_curve(df.d.values, df.ttm.values.astype(float),
                                df.m_est.values.astype(float), df.w.values.astype(float))
    df["cvfit"], df["cvn"] = fit, nn
    df["dev"] = df.m_est - df.cvfit
    return df[df.cvfit.notna()].copy()


for cut in ["1500", "1530"]:
    df = build(cut)
    for a, b in (("2025-07-01", "2025-12-31"), ("2026-01-01", "2026-09-30")):
        tr = df[df.d < a].copy(); te = df[(df.d >= a) & (df.d <= b)].copy()
        tr["e"] = tr.y - tr.cvfit
        m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.04, max_depth=4,
                                          min_samples_leaf=60, l2_regularization=2.0, random_state=0)
        m.fit(tr[FEAT_Q], tr.e)
        y = te.y.to_numpy(); day = te.d.to_numpy()
        f_cv = te.cvfit.to_numpy()
        f_ml = f_cv + m.predict(te[FEAT_Q])
        f_ru = te.rule.to_numpy()
        f_bl = np.where(te.both == 1, 0.5 * te.m_est + 0.5 * te.cvfit, te.cvfit).astype(float)
        print(f"\n===== {cut[:2]}:{cut[2:]}  시험 {a[:7]}~{b[:7]}   종목일 {len(te):,} · 영업일 {te.d.nunique()}")
        r = cw(y, f_cv, f_ml, day)
        print(f"  [포함 · Clark-West]  커브  vs  커브+ML       CW = {r['stat']:5.2f}   p(단측) = {r['p']:.4f}   (NW lag {r['lag']})")
        r = cw(y, f_cv, f_bl, day)
        print(f"  [포함 · Clark-West]  커브  vs  블렌드(반반)   CW = {r['stat']:5.2f}   p(단측) = {r['p']:.4f}")
        for loss in ("mse", "mae"):
            r = dm(y - f_ru, y - f_ml, day, loss)
            print(f"  [비포함 · DM+HLN {loss}] 구간규칙 vs 커브+ML  t = {r['stat']:5.2f}   p(양측) = {r['p']:.3f}   T={r['T']}")
        for loss in ("mse", "mae"):
            r = dm(y - f_ru, y - f_bl, day, loss)
            print(f"  [비포함 · DM+HLN {loss}] 구간규칙 vs 블렌드   t = {r['stat']:5.2f}   p(양측) = {r['p']:.3f}")
