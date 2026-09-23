"""구간추정 v2 — 고정 보정이 무너진다. 셋을 더 붙인다.

  C. 움직이는 창   최근 N영업일 잔차로만 보정
  D. 정규화 등각   잔차를 «요즘 얼마나 움직이나»로 나눈 뒤 보정 (폭이 스스로 늘고 준다)
  E. ACI          맞은 날/터진 날을 보고 목표수준을 매일 갱신 (Gibbs-Candes)
전 구간을 하루씩 앞으로 걸으며 채점한다. 보정은 언제나 «그날 이전»만 쓴다.
"""
import numpy as np, pandas as pd

WIN = 120          # 움직이는 창 (영업일)
GAMMA = 0.03       # ACI 갱신 속도
START = "2025-01-02"


def conf_q(res, alpha):
    n = len(res)
    if n < 50:
        return np.nan
    k = int(np.ceil((n + 1) * (1 - alpha))) - 1
    return np.sort(np.abs(res))[min(k, n - 1)]


def run(cut, alpha):
    P = pd.read_parquet("timing_panel.parquet")
    D = P[P.cut == cut].copy().sort_values("d")
    D["res"] = D.est - D.y
    days = np.array(sorted(D.d.unique()))
    by = {d: g for d, g in D.groupby("d")}
    hist = []                                   # (day, res array, scale)
    out = {k: [] for k in ("fix", "roll", "norm", "aci")}
    wid = {k: [] for k in out}
    a_t = alpha
    fix_q = None
    for i, d in enumerate(days):
        g = by[d]
        past = [h for h in hist if h[0] < d]
        if len(past) >= 60 and str(d)[:10] >= START:
            allr = np.concatenate([h[1] for h in past])
            if fix_q is None:                    # 고정: 첫 시점에 한 번 정하고 그대로
                fix_q = conf_q(allr, alpha)
            rec = [h for h in past[-WIN:]]
            rq = conf_q(np.concatenate([h[1] for h in rec]), alpha)
            # 정규화: 최근 20일 평균 |잔차| 를 척도로
            sc_hist = np.array([h[2] for h in past])
            s_now = np.mean(sc_hist[-20:])
            z = np.concatenate([h[1] / max(h[2], 1e-6) for h in rec])
            zq = conf_q(z, alpha) * s_now
            aq = conf_q(np.concatenate([h[1] for h in rec]), min(max(a_t, 0.001), 0.5))
            y = g.y.values; e = g.est.values
            for k, q in (("fix", fix_q), ("roll", rq), ("norm", zq), ("aci", aq)):
                if not np.isfinite(q):
                    continue
                cov = ((y >= e - q) & (y <= e + q))
                out[k].append(cov.mean()); wid[k].append(2 * q)
            if np.isfinite(aq):
                err = 1.0 - ((y >= e - aq) & (y <= e + aq)).mean()
                a_t = a_t + GAMMA * (alpha - err)
        hist.append((d, g.res.values, np.mean(np.abs(g.res.values))))
    return {k: (np.mean(out[k]), np.mean(wid[k]), len(out[k])) for k in out}


for cut in ["11:00", "13:00"]:
    for alpha, nom in ((0.20, 80), (0.10, 90)):
        r = run(cut, alpha)
        print(f"\n--- {cut}  목표 {nom}%   (채점 {r['fix'][2]}영업일, {START}~)")
        for k, nm in (("fix", "고정 보정(v1)"), ("roll", f"움직이는 창 {WIN}일"),
                      ("norm", "정규화 등각"), ("aci", f"ACI γ={GAMMA}")):
            c, w, n = r[k]
            print(f"   {nm:18s} 실제 커버리지 {100*c:5.1f}%   평균 폭 {w:5.2f}bp")
