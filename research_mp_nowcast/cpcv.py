"""2번 — 조합형 purged 교차검증 (CPCV).

날짜를 N=10 덩어리로 자르고, 그중 2덩어리씩을 시험으로 쓴다 -> C(10,2)=45 조각.
경계에서 새는 걸 막는다:
  purge   시험 블록 앞뒤 2영업일을 학습에서 버린다.
          (라벨은 당일이지만 res_prev·dmp_prev 가 D-1·D-2 를 읽으므로 2일)
  embargo 시험 블록 뒤로 5영업일 더 버린다 (계열상관 누수).
CPCV 는 walk-forward 가 아니다. 미래로 학습하는 조각이 있다.
묻는 것은 «성적이 자르기 하나에 기댄 것인가» 이다.
"""
import itertools, numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from train3 import FEAT_Q
from dmtest import build, dm, cw

N_GROUP, K_TEST, PURGE, EMBARGO = 10, 2, 2, 5


def run(cut):
    df = build(cut)
    days = np.array(sorted(df.d.unique()))
    pos = {d: i for i, d in enumerate(days)}
    df["di"] = df.d.map(pos)
    groups = np.array_split(np.arange(len(days)), N_GROUP)
    rows = []
    for combo in itertools.combinations(range(N_GROUP), K_TEST):
        tidx = np.concatenate([groups[g] for g in combo])
        blocked = set()
        for t in tidx:
            blocked.update(range(t - PURGE, t + PURGE + EMBARGO + 1))
        te = df[df.di.isin(tidx)]
        tr = df[~df.di.isin(blocked)]
        if len(te) < 200 or len(tr) < 2000:
            continue
        trc = tr.copy(); trc["e"] = trc.y - trc.cvfit
        m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.04, max_depth=4,
                                          min_samples_leaf=60, l2_regularization=2.0,
                                          random_state=0).fit(trc[FEAT_Q], trc.e)
        y = te.y.to_numpy(); day = te.d.to_numpy()
        f = {"rule": te.rule.to_numpy(), "cv": te.cvfit.to_numpy(),
             "blend": np.where(te.both == 1, 0.5 * te.m_est + 0.5 * te.cvfit, te.cvfit).astype(float),
             "ml": te.cvfit.to_numpy() + m.predict(te[FEAT_Q])}
        r = dict(combo="+".join(map(str, combo)), n_te=len(te), n_tr=len(tr), days=te.d.nunique())
        for k, v in f.items():
            e = np.abs(v - y)
            r[f"med_{k}"] = np.median(e); r[f"mae_{k}"] = e.mean()
            r[f"rmse_{k}"] = float(np.sqrt(((v - y) ** 2).mean()))
        r["dm_rule_ml_mae"] = dm(y - f["rule"], y - f["ml"], day, "mae")["stat"]
        r["dm_rule_ml_mse"] = dm(y - f["rule"], y - f["ml"], day, "mse")["stat"]
        r["dm_rule_bl_mae"] = dm(y - f["rule"], y - f["blend"], day, "mae")["stat"]
        r["cw_cv_ml"] = cw(y, f["cv"], f["ml"], day)["stat"]
        rows.append(r)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    for cut in ["1530", "1500"]:
        r = run(cut); r.to_csv(f"cpcv_{cut}.csv", index=False)
        print(f"\n===== CPCV {cut[:2]}:{cut[2:]}   조각 {len(r)}개  "
              f"(시험 평균 {r.n_te.mean():.0f}종목일 · {r.days.mean():.0f}영업일 / 학습 {r.n_tr.mean():.0f})")
        print("  모형별 성적 분포 (조각 45개)")
        print(f"  {'':10s} {'중앙의 중앙':>10s} {'최악조각':>9s} {'평균의 중앙':>10s} {'최악조각':>9s}")
        for k, nm in [("rule", "구간규칙"), ("cv", "커브"), ("blend", "블렌드"), ("ml", "커브+ML")]:
            print(f"  {nm:10s} {r[f'med_{k}'].median():10.2f} {r[f'med_{k}'].max():9.2f} "
                  f"{r[f'mae_{k}'].median():10.2f} {r[f'mae_{k}'].max():9.2f}")
        print("\n  ML 이 규칙을 이긴 조각:  중앙기준 %d/%d (%.0f%%)   평균기준 %d/%d (%.0f%%)"
              % ((r.med_ml < r.med_rule).sum(), len(r), 100 * (r.med_ml < r.med_rule).mean(),
                 (r.mae_ml < r.mae_rule).sum(), len(r), 100 * (r.mae_ml < r.mae_rule).mean()))
        print("  블렌드가 규칙을 이긴 조각: 평균기준 %d/%d (%.0f%%)"
              % ((r.mae_blend < r.mae_rule).sum(), len(r), 100 * (r.mae_blend < r.mae_rule).mean()))
        for c, nm in [("dm_rule_ml_mae", "DM 규칙vsML (MAE)"), ("dm_rule_ml_mse", "DM 규칙vsML (MSE)"),
                      ("dm_rule_bl_mae", "DM 규칙vs블렌드"), ("cw_cv_ml", "CW 커브vsML")]:
            v = r[c]
            print(f"  {nm:20s} 중앙 t {v.median():5.2f}   [p5 {v.quantile(.05):5.2f}, p95 {v.quantile(.95):5.2f}]"
                  f"   t>1.96 인 조각 {100*(v>1.96).mean():3.0f}%")
