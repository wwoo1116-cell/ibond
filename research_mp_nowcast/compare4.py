"""규칙 · 커브 · 블렌드 · 커브+ML 을 같은 시험구간에서 네 지표로."""
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from train3 import loo_wmedian_curve, mid_est, FEAT_Q
from dmtest import build

rows=[]
for cut in ["1500","1530"]:
    df = build(cut)
    for a,b in (("2025-07-01","2025-12-31"),("2026-01-01","2026-09-30")):
        tr=df[df.d<a].copy(); te=df[(df.d>=a)&(df.d<=b)].copy()
        tr["e"]=tr.y-tr.cvfit
        m=HistGradientBoostingRegressor(max_iter=300,learning_rate=0.04,max_depth=4,
            min_samples_leaf=60,l2_regularization=2.0,random_state=0).fit(tr[FEAT_Q],tr.e)
        y=te.y.to_numpy()
        P={"구간규칙":te.rule.to_numpy(),"커브":te.cvfit.to_numpy(),
           "블렌드":np.where(te.both==1,0.5*te.m_est+0.5*te.cvfit,te.cvfit).astype(float),
           "커브+ML":te.cvfit.to_numpy()+m.predict(te[FEAT_Q])}
        for nm,f in P.items():
            e=np.abs(f-y)
            rows.append(dict(cut=f"{cut[:2]}:{cut[2:]}",fold=a[:7],model=nm,n=len(te),
                             median=np.median(e),mean=e.mean(),p90=np.quantile(e,.9),
                             p99=np.quantile(e,.99),rmse=np.sqrt(((f-y)**2).mean()),
                             worst=e.max()))
r=pd.DataFrame(rows); pd.set_option("display.width",220)
for (c,f),g in r.groupby(["cut","fold"]):
    print(f"\n=== {c}  시험 {f}~  (n={g.n.iloc[0]:,}) ===")
    print(g[["model","median","mean","p90","p99","rmse","worst"]].round(2).to_string(index=False))
r.to_csv("compare4.csv",index=False)
