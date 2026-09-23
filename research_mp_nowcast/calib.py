"""화면에 찍을 밴드 — 표본밖(2025-07~) 채점, 시각 x 호가상태."""
import numpy as np, pandas as pd
from train3 import loo_wmedian_curve, mid_est

rows = []
for cut in ["1100", "1300", "1500", "1530"]:
    df = pd.read_parquet(f"panel_{cut}.parquet").sort_values(["d", "ttm"]).reset_index(drop=True)
    df["m_est"] = mid_est(df)
    df["w"] = np.where(df.both == 1, 1.0, 0.45) * (0.5 + 0.5 * df.q_tlast / 480.0)
    fit, nn = loo_wmedian_curve(df.d.values, df.ttm.values.astype(float),
                               df.m_est.values.astype(float), df.w.values.astype(float))
    df["cvfit"] = fit
    df = df[df.cvfit.notna() & (df.d >= "2025-07-01")].copy()
    # 화면이 실제로 쓸 추정: 자기 호가가 있으면 커브와 섞고, 없으면 커브만
    df["est"] = np.where(df.both == 1, 0.5 * df.m_est + 0.5 * df.cvfit, df.cvfit)
    df["st"] = np.where(df.both == 1, "양면", np.where(df.m_est.notna(), "한쪽", "호가없음"))
    df["err"] = (df.est - df.y).abs()
    for st, g in df.groupby("st"):
        rows.append(dict(cut=f"{cut[:2]}:{cut[2:]}", state=st, n=len(g),
                         med=g.err.median(), p75=g.err.quantile(.75), p90=g.err.quantile(.9)))
    rows.append(dict(cut=f"{cut[:2]}:{cut[2:]}", state="전체", n=len(df),
                     med=df.err.median(), p75=df.err.quantile(.75), p90=df.err.quantile(.9)))
r = pd.DataFrame(rows)
print(r.pivot_table(index="cut", columns="state", values=["med", "p90", "n"]).round(2).to_string())
r.to_csv("calib.csv", index=False)
