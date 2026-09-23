"""Train: yesterday MP + today's quotes up to t  ->  today's closing MP move (bp).

Walk-forward by time.  Compared against the rules the model has to beat.
"""
import sys, numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

FEATS = ["ttm", "q_n", "q_first", "q_last", "q_lo", "q_hi", "q_std", "q_tlast", "q_tfirst",
         "off_last", "off_n", "off_t", "bid_last", "bid_n", "bid_t", "mid", "both", "qspread",
         "cv_n", "cvn_n", "cv_b", "cvn_b", "cv_s", "cv_l", "dmp_prev", "res_prev"]


def bucket_rule(df):
    """앞서 쓴 손 규칙: 만기구간 LOO 중앙값."""
    d = df.copy()
    d["b"] = pd.cut(d.ttm, [0, 1, 2, 3, 5, 10, 31])
    g = d.groupby(["d", "b"], observed=True)["mid"]
    med = g.transform("median")
    n = g.transform("count")
    return np.where(n >= 2, med, 0.0)


def score(name, yhat, y):
    e = np.abs(yhat - y)
    return dict(model=name, n=len(y), median=np.median(e), mae=e.mean(),
                rmse=float(np.sqrt(((yhat - y) ** 2).mean())),
                r2=1 - ((yhat - y) ** 2).sum() / (y ** 2).sum())


def run(cut, folds=(("2025-07-01", "2025-12-31"), ("2026-01-01", "2026-09-30"))):
    df = pd.read_parquet(f"panel_{cut}.parquet")
    df["rule"] = bucket_rule(df)
    rows, imp = [], None
    for a, b in folds:
        tr = df[df.d < a]
        te = df[(df.d >= a) & (df.d <= b)]
        if len(te) == 0:
            continue
        m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, max_depth=6,
                                          min_samples_leaf=40, l2_regularization=1.0,
                                          random_state=0)
        m.fit(tr[FEATS], tr.y)
        p = m.predict(te[FEATS])
        for nm, yh in [("(0) yesterday MP", np.zeros(len(te))),
                       ("(1) bucket-median rule", te.rule.to_numpy()),
                       ("(2) own book mid", te["mid"].fillna(te.q_last).to_numpy()),
                       ("(3) ML", p)]:
            r = score(nm, yh, te.y.to_numpy()); r["fold"] = f"{a[:7]}~{b[:7]}"; r["ntr"] = len(tr)
            rows.append(r)
        imp = pd.Series(
            dict(zip(FEATS, np.zeros(len(FEATS)))))  # placeholder, permutation below
        if b.startswith("2026"):
            from sklearn.inspection import permutation_importance
            pi = permutation_importance(m, te[FEATS], te.y, n_repeats=5, random_state=0,
                                        scoring="neg_mean_absolute_error")
            imp = pd.Series(pi.importances_mean, index=FEATS).sort_values(ascending=False)
    out = pd.DataFrame(rows)
    print(f"\n===== cutoff {cut[:2]}:{cut[2:]} =====")
    for f in out.fold.unique():
        s = out[out.fold == f]
        print(f"  test {f}   n={s.n.iloc[0]:,}  train={s.ntr.iloc[0]:,}")
        for _, r in s.iterrows():
            print(f"     {r.model:24s} median {r['median']:5.2f}  MAE {r.mae:5.2f}  "
                  f"RMSE {r.rmse:5.2f}  R2 {r.r2:6.3f}")
    return out, imp


if __name__ == "__main__":
    allout = []
    for cut in ["1100", "1300", "1500", "1530"]:
        o, imp = run(cut)
        o["cut"] = cut
        allout.append(o)
        if cut == "1530":
            print("\n  permutation importance (2026 test, MAE bp):")
            print("    " + "  ".join(f"{k}:{v:.2f}" for k, v in imp.head(10).items()))
    pd.concat(allout).to_csv("scores.csv", index=False)
