"""모형 여러 종을 같은 판에 — 결측 수리판.

수리 1: 커브 적합이 안 된 행을 버리지 않는다. 구간규칙 -> 0 순으로 되돌린다.
수리 2: 선형 모형에는 중앙값 대치 + «결측이었다» 표시열을 함께 준다.
        트리 계열은 결측을 그대로 먹는다(HistGB·XGB·LGBM). RF/ET/GB 는 못 먹어서 대치판을 쓴다.
"""
import warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from sklearn.linear_model import Ridge, ElasticNet
from sklearn.ensemble import (RandomForestRegressor, ExtraTreesRegressor,
                              HistGradientBoostingRegressor, GradientBoostingRegressor)
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
import xgboost as xgb, lightgbm as lgb
from train3 import loo_wmedian_curve, mid_est

FEAT = ["ttm", "q_n", "q_first", "q_last", "q_lo", "q_hi", "q_std", "q_tlast", "q_tfirst",
        "off_last", "off_n", "off_t", "bid_last", "bid_n", "bid_t", "m_est", "both", "qspread",
        "cvfit", "dev", "nmkt", "dmp_prev", "res_prev", "rule"]


def prep(cut):
    P = pd.read_parquet(f"panel_{cut}.parquet").sort_values(["d", "ttm"]).reset_index(drop=True)
    P["m_est"] = mid_est(P)
    P["w"] = np.where(P.both == 1, 1.0, 0.45) * (0.5 + 0.5 * P.q_tlast / 480.0)
    fit, _ = loo_wmedian_curve(P.d.values, P.ttm.values.astype(float),
                               P.m_est.values.astype(float), P.w.values.astype(float))
    P["cvfit_raw"] = fit
    # ★수리: 버리지 않고 되돌린다
    P["cv_src"] = np.where(P.cvfit_raw.notna(), 0, np.where(P.rule.notna(), 1, 2))
    P["cvfit"] = P.cvfit_raw.fillna(P.rule).fillna(0.0)
    P["dev"] = P.m_est - P.cvfit
    P["nmkt"] = P.groupby("d")["c"].transform("size")
    P["blend"] = np.where(P.both == 1, 0.5 * P.m_est + 0.5 * P.cvfit, P.cvfit)
    return P


def imputed(df):
    X = df[FEAT].copy()
    for c in FEAT:
        if X[c].isna().any():
            X[c + "_na"] = X[c].isna().astype(int)
    return X


MODELS = {
    "Ridge":      ("imp", lambda: make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=10.0))),
    "ElasticNet": ("imp", lambda: make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), ElasticNet(alpha=0.05, l1_ratio=0.5, max_iter=5000))),
    "RandomForest": ("imp", lambda: make_pipeline(SimpleImputer(strategy="median"), RandomForestRegressor(n_estimators=300, min_samples_leaf=20, n_jobs=-1, random_state=0))),
    "ExtraTrees": ("imp", lambda: make_pipeline(SimpleImputer(strategy="median"), ExtraTreesRegressor(n_estimators=300, min_samples_leaf=20, n_jobs=-1, random_state=0))),
    "GB(비구간화)": ("imp", lambda: make_pipeline(SimpleImputer(strategy="median"), GradientBoostingRegressor(n_estimators=300, learning_rate=0.04, max_depth=3, min_samples_leaf=40, random_state=0))),
    "HistGB":     ("raw", lambda: HistGradientBoostingRegressor(max_iter=300, learning_rate=0.04, max_depth=4, min_samples_leaf=60, l2_regularization=2.0, random_state=0)),
    "XGBoost":    ("raw", lambda: xgb.XGBRegressor(n_estimators=400, learning_rate=0.04, max_depth=4, subsample=0.8, colsample_bytree=0.8, reg_lambda=2.0, n_jobs=-1, random_state=0)),
    "LightGBM":   ("raw", lambda: lgb.LGBMRegressor(n_estimators=400, learning_rate=0.04, max_depth=5, num_leaves=31, min_child_samples=40, reg_lambda=2.0, n_jobs=-1, random_state=0, verbose=-1)),
}
FOLDS = [("2025-07-01", "2025-12-31"), ("2026-01-01", "2026-09-30")]


def score(f, y):
    e = np.abs(f - y)
    return np.median(e), e.mean(), float(np.sqrt(((f - y) ** 2).mean()))


if __name__ == "__main__":
    for cut in ["1300", "1600"]:
        P = prep(cut)
        print(f"\n{'='*86}\n컷오프 {cut[:2]}:{cut[2:]}   전체 {len(P):,}행 "
              f"(커브 적합 {100*(P.cv_src==0).mean():.1f}% · 규칙 되돌림 {100*(P.cv_src==1).mean():.1f}% · 0 {100*(P.cv_src==2).mean():.1f}%)")
        for a, b in FOLDS:
            tr = P[P.d < a].copy(); te = P[(P.d >= a) & (P.d <= b)].copy()
            tr["e"] = tr.y - tr.cvfit
            Xtr_r, Xte_r = tr[FEAT], te[FEAT]
            Xtr_i, Xte_i = imputed(tr), imputed(te)
            Xte_i = Xte_i.reindex(columns=Xtr_i.columns, fill_value=0)
            print(f"\n  시험 {a[:7]}~{b[:7]}  학습 {len(tr):,} · 시험 {len(te):,} · |y|중앙 {te.y.abs().median():.2f}bp")
            base = [("구간규칙", te.rule.values), ("커브", te.cvfit.values), ("블렌드", te.blend.values)]
            for nm, f in base:
                m, mn, r = score(f, te.y.values)
                print(f"     {nm:14s} 중앙 {m:5.2f}  평균 {mn:5.2f}  RMSE {r:5.2f}")
            for nm, (kind, mk) in MODELS.items():
                Xtr, Xte = (Xtr_r, Xte_r) if kind == "raw" else (Xtr_i, Xte_i)
                mdl = mk(); mdl.fit(Xtr, tr.e)
                f = te.cvfit.values + mdl.predict(Xte)
                m, mn, r = score(f, te.y.values)
                print(f"     {nm:14s} 중앙 {m:5.2f}  평균 {mn:5.2f}  RMSE {r:5.2f}")
