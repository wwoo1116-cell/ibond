"""구간규칙을 leave-one-out 중앙값으로 고친다.
이전 판은 자기 mid 를 중앙값에 포함시켜 상대에게 자기 답을 조금 보여 주고 있었다."""
import numpy as np, pandas as pd

def loo_median(v):
    """각 원소에 대해 자기를 뺀 중앙값."""
    v = np.asarray(v, float)
    out = np.full(len(v), np.nan)
    for i in range(len(v)):
        o = np.delete(v, i)
        o = o[~np.isnan(o)]
        if len(o):
            out[i] = np.median(o)
    return out

for c in ["1100","1300","1500","1530"]:
    d = pd.read_parquet(f"panel_{c}.parquet")
    d["_b"] = pd.cut(d.ttm, [0,1,2,3,5,10,31]).astype(str)
    old = d["rule"].copy()
    r = np.full(len(d), np.nan)
    for _, idx in d.groupby(["d","_b"]).groups.items():
        pos = d.index.get_indexer(idx)
        r[pos] = loo_median(d["mid"].to_numpy()[pos])
    d["rule"] = np.where(np.isnan(r), 0.0, r)
    d.drop(columns=["_b"]).to_parquet(f"panel_{c}.parquet", index=False)
    print(f"{c}: rule 재계산  자기포함판과 평균차 {np.nanmean(np.abs(old-d['rule'])):.3f}bp  "
          f"결측->0 {int(np.isnan(r).sum()):,}/{len(d):,}")
