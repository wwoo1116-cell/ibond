"""FLAML(AutoML) 과 TabPFN 을 같은 폴드에 올린다."""
import warnings, time, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from zoo import prep, imputed, FEAT, score, FOLDS

BUDGET = 180


def run(cut):
    P = prep(cut)
    print(f"\n{'='*70}\n컷오프 {cut[:2]}:{cut[2:]}")
    for a, b in FOLDS:
        tr = P[P.d < a].copy(); te = P[(P.d >= a) & (P.d <= b)].copy()
        tr["e"] = tr.y - tr.cvfit
        Xi_tr, Xi_te = imputed(tr), imputed(te)
        Xi_te = Xi_te.reindex(columns=Xi_tr.columns, fill_value=0)
        print(f"\n 시험 {a[:7]}~  학습 {len(tr):,} / 시험 {len(te):,}")
        m, mn, r = score(te.blend.values, te.y.values)
        print(f"   {'블렌드(상대)':16s} 중앙 {m:5.2f}  평균 {mn:5.2f}  RMSE {r:5.2f}")

        from flaml import AutoML
        t0 = time.time()
        am = AutoML()
        am.fit(X_train=tr[FEAT], y_train=tr.e, task="regression", time_budget=BUDGET,
               metric="mae", verbose=0, seed=0)
        f = te.cvfit.values + am.predict(te[FEAT])
        m, mn, r = score(f, te.y.values)
        print(f"   {'FLAML':16s} 중앙 {m:5.2f}  평균 {mn:5.2f}  RMSE {r:5.2f}"
              f"   [{am.best_estimator} · {time.time()-t0:.0f}s]")

        try:
            from tabpfn import TabPFNRegressor
            t0 = time.time()
            n = min(len(tr), 8000)
            s = tr.sample(n, random_state=0)
            reg = TabPFNRegressor(device="cpu", ignore_pretraining_limits=True)
            reg.fit(Xi_tr.loc[s.index].values, s.e.values)
            pred = np.concatenate([reg.predict(Xi_te.values[i:i+2000])
                                   for i in range(0, len(Xi_te), 2000)])
            f = te.cvfit.values + pred
            m, mn, r = score(f, te.y.values)
            print(f"   {'TabPFN':16s} 중앙 {m:5.2f}  평균 {mn:5.2f}  RMSE {r:5.2f}"
                  f"   [학습 {n:,}행 · {time.time()-t0:.0f}s]")
        except Exception as ex:
            print(f"   TabPFN 실패: {type(ex).__name__}: {str(ex)[:150]}")


if __name__ == "__main__":
    for cut in ["1600", "1300"]:
        run(cut)
