"""최종 채점 — 로버스트 커브 + ML 잔차, 호가만.  날짜 단위 짝비교로 유의성까지."""
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from train3 import loo_wmedian_curve, mid_est, FEAT_Q, sc

FOLDS = [("2025-07-01", "2025-12-31"), ("2026-01-01", "2026-09-30")]


def prep(cut):
    df = pd.read_parquet(f"panel_{cut}.parquet").sort_values(["d", "ttm"]).reset_index(drop=True)
    df["m_est"] = mid_est(df)
    df["w"] = np.where(df.both == 1, 1.0, 0.45) * (0.5 + 0.5 * df.q_tlast / 480.0)
    fit, nn = loo_wmedian_curve(df.d.values, df.ttm.values.astype(float),
                                df.m_est.values.astype(float), df.w.values.astype(float))
    df["cvfit"], df["cvn"] = fit, nn
    df["dev"] = df.m_est - df.cvfit
    return df[df.cvfit.notna()].copy()


rows = []
for cut in ["1100", "1300", "1500", "1530"]:
    df = prep(cut)
    for a, b in FOLDS:
        tr = df[df.d < a].copy(); te = df[(df.d >= a) & (df.d <= b)].copy()
        if len(te) < 100:
            continue
        tr["e"] = tr.y - tr.cvfit
        m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.04, max_depth=4,
                                          min_samples_leaf=60, l2_regularization=2.0, random_state=0)
        m.fit(tr[FEAT_Q], tr.e)
        te["p_ml"] = te.cvfit + m.predict(te[FEAT_Q])
        te["p_rule"] = te.rule
        te["p_cv"] = te.cvfit
        y = te.y
        for nm in ["rule", "cv", "ml"]:
            te[f"e_{nm}"] = (te[f"p_{nm}"] - y).abs()
        dly = te.groupby("d")[["e_rule", "e_ml"]].mean()
        dd = dly.e_rule - dly.e_ml
        t = dd.mean() / (dd.std(ddof=1) / np.sqrt(len(dd)))
        rows.append(dict(cut=f"{cut[:2]}:{cut[2:]}", fold=f"{a[:7]}~{b[:7]}", n=len(te),
                         days=len(dly), y_med=y.abs().median(),
                         yest=y.abs().median(),
                         med_rule=te.e_rule.median(), med_cv=te.e_cv.median(), med_ml=te.e_ml.median(),
                         mae_rule=te.e_rule.mean(), mae_ml=te.e_ml.mean(),
                         rmse_rule=float(np.sqrt((te.p_rule - y).pow(2).mean())),
                         rmse_ml=float(np.sqrt((te.p_ml - y).pow(2).mean())),
                         win_day=float((dd > 0).mean()), t_stat=float(t)))
r = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(r.round(3).to_string(index=False))
r.to_csv("eval_final.csv", index=False)
