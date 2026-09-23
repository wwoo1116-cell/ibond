"""ACI 구간을 (a) 아무것도 안 한 경우와 견주고 (b) 책 두께로 가른다."""
import numpy as np, pandas as pd
WIN, GAMMA, START = 120, 0.03, "2025-01-02"


def conf_q(res, a):
    n = len(res)
    if n < 50: return np.nan
    k = int(np.ceil((n + 1) * (1 - a))) - 1
    return np.sort(np.abs(res))[min(k, n - 1)]


def aci(D, alpha, use_est=True, group=None):
    """group 이 주어지면 칸마다 따로 ACI 를 돌린다."""
    D = D.copy()
    D["e"] = D.est if use_est else 0.0
    D["res"] = D.e - D.y
    keys = [None] if group is None else list(D[group].dropna().unique())
    res = {}
    for kk in keys:
        S = D if kk is None else D[D[group] == kk]
        days = np.array(sorted(S.d.unique()))
        by = {d: g for d, g in S.groupby("d")}
        hist, cov, wid, a_t = [], [], [], alpha
        for d in days:
            g = by[d]
            past = [h for h in hist if h[0] < d][-WIN:]
            if len(past) >= 40 and str(d)[:10] >= START:
                q = conf_q(np.concatenate([h[1] for h in past]), min(max(a_t, .001), .5))
                if np.isfinite(q):
                    ok = (g.y >= g.e - q) & (g.y <= g.e + q)
                    cov.append(ok.mean()); wid.append(2 * q)
                    a_t = a_t + GAMMA * (alpha - (1 - ok.mean()))
            hist.append((d, g.res.values))
        res[kk] = (np.mean(cov) if cov else np.nan, np.mean(wid) if wid else np.nan, len(cov))
    return res


P = pd.read_parquet("timing_panel.parquet")
P["nb"] = pd.cut(P.nmkt, [0, 20, 30, 200], labels=["얇음(~20종)", "보통(21-30)", "두꺼움(31종+)"])
for cut in ["11:00", "13:00", "15:30"]:
    D = P[P.cut == cut]
    print(f"\n════ {cut} ════  (종목일 {len(D):,})")
    for alpha, nom in ((0.20, 80), (0.10, 90)):
        b = aci(D, alpha, use_est=False)[None]
        e = aci(D, alpha, use_est=True)[None]
        print(f"  목표 {nom}%   아무것도 안 함: 실제 {100*b[0]:.1f}% · 폭 {b[1]:.2f}bp"
              f"   →   추정 사용: 실제 {100*e[0]:.1f}% · 폭 {e[1]:.2f}bp"
              f"   (폭 {100*(1-e[1]/b[1]):.0f}% 축소)")
    print("  책 두께별 (목표 80%)")
    for k, v in aci(D, 0.20, True, group="nb").items():
        if np.isfinite(v[1]):
            print(f"     {str(k):16s} 실제 {100*v[0]:5.1f}%   폭 {v[1]:5.2f}bp  (±{v[1]/2:.2f})   채점 {v[2]}일")
