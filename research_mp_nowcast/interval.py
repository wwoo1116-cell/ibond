"""13시 이전 구간추정.

과녁  오늘 마감 민평3사 (= 국고통_민평, 오늘 확인)
방식  A. Mondrian 분할등각 — 책 두께 칸별로 잔차분위수를 그대로 구간으로
      B. CQR — 분위수 부스팅을 등각으로 보정
규율  보정(calibration)은 시험구간보다 항상 «앞»에서만 뽑는다.
"""
import numpy as np, pandas as pd
from sklearn.ensemble import GradientBoostingRegressor

CUTS = ["10:00", "11:00", "12:00", "13:00"]
FOLDS = [("2025-07-01", "2025-12-31"), ("2026-01-01", "2026-09-30")]
FEAT = ["ttm", "q_n", "both", "nmkt", "cv", "m_est"]


def mondrian(cal, te, alpha, key="nb"):
    """칸별 |잔차| 의 등각분위수. 표본 적은 칸은 전체로 뒤로 물러난다."""
    n_all = len(cal)
    k_all = int(np.ceil((n_all + 1) * (1 - alpha))) - 1
    q_all = np.sort(np.abs(cal.res.values))[min(k_all, n_all - 1)]
    q = {}
    for g, c in cal.groupby(key, observed=True):
        n = len(c)
        if n < 200:
            q[g] = q_all; continue
        k = int(np.ceil((n + 1) * (1 - alpha))) - 1
        q[g] = np.sort(np.abs(c.res.values))[min(k, n - 1)]
    return te[key].map(q).fillna(q_all).to_numpy()


def cqr(cal_fit, cal_cal, te, alpha):
    """분위수회귀 두 개를 등각으로 보정(CQR, Romano et al. 2019 방식)."""
    lo_m = GradientBoostingRegressor(loss="quantile", alpha=alpha / 2, n_estimators=200,
                                     max_depth=3, learning_rate=0.05, random_state=0)
    hi_m = GradientBoostingRegressor(loss="quantile", alpha=1 - alpha / 2, n_estimators=200,
                                     max_depth=3, learning_rate=0.05, random_state=0)
    lo_m.fit(cal_fit[FEAT], cal_fit.y); hi_m.fit(cal_fit[FEAT], cal_fit.y)
    lo_c, hi_c = lo_m.predict(cal_cal[FEAT]), hi_m.predict(cal_cal[FEAT])
    E = np.maximum(lo_c - cal_cal.y.values, cal_cal.y.values - hi_c)
    n = len(E); k = int(np.ceil((n + 1) * (1 - alpha))) - 1
    Q = np.sort(E)[min(k, n - 1)]
    return lo_m.predict(te[FEAT]) - Q, hi_m.predict(te[FEAT]) + Q


P = pd.read_parquet("timing_panel.parquet")
P["res"] = P.est - P.y
P["nb"] = pd.cut(P.nmkt, [0, 15, 25, 35, 200], labels=["~15", "16-25", "26-35", "36+"])
rows = []
for cut in CUTS:
    D = P[P.cut == cut].copy()
    for a, b in FOLDS:
        cal = D[D.d < a]; te = D[(D.d >= a) & (D.d <= b)]
        if len(te) < 300 or len(cal) < 1000:
            continue
        cut_i = int(len(cal) * 0.6)
        cal_fit, cal_cal = cal.iloc[:cut_i], cal.iloc[cut_i:]
        for alpha, nom in ((0.20, 80), (0.10, 90)):
            # 기준: 칸 구분 없는 상수 밴드
            n = len(cal); k = int(np.ceil((n + 1) * (1 - alpha))) - 1
            q0 = np.sort(np.abs(cal.res.values))[min(k, n - 1)]
            cov0 = ((te.y >= te.est - q0) & (te.y <= te.est + q0)).mean()
            # A. Mondrian
            qm = mondrian(cal, te, alpha)
            covm = ((te.y >= te.est - qm) & (te.y <= te.est + qm)).mean()
            # B. CQR
            lo, hi = cqr(cal_fit, cal_cal, te, alpha)
            covc = ((te.y >= lo) & (te.y <= hi)).mean()
            rows.append(dict(cut=cut, fold=a[:7], nom=nom, n=len(te),
                             cov_const=cov0, w_const=2 * q0,
                             cov_mond=covm, w_mond=float(np.mean(2 * qm)),
                             cov_cqr=covc, w_cqr=float(np.mean(hi - lo))))
R = pd.DataFrame(rows); R.to_csv("interval.csv", index=False)
pd.set_option("display.width", 220)
for nom in (80, 90):
    print(f"\n===== 목표 커버리지 {nom}%  (구간 폭은 bp) =====")
    s = R[R.nom == nom]
    print(f"{'시각':>6} {'시험':>8} {'n':>6} | {'상수밴드':>16} | {'책두께칸':>16} | {'CQR':>16}")
    print(f"{'':>6} {'':>8} {'':>6} | {'실제%':>7}{'폭':>9} | {'실제%':>7}{'폭':>9} | {'실제%':>7}{'폭':>9}")
    for _, r in s.iterrows():
        print(f"{r.cut:>6} {r.fold:>8} {r.n:6,} | {100*r.cov_const:6.1f}%{r.w_const:9.2f} | "
              f"{100*r.cov_mond:6.1f}%{r.w_mond:9.2f} | {100*r.cov_cqr:6.1f}%{r.w_cqr:9.2f}")
