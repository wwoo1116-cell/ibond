"""§11 지표 1차 — 체결 귀속이 열어 준 셋을 국고 전 이력에서 잰다. [K-Orderbook+++ 2026-09-15]

v12(체결 귀속)는 «체결은 삭제가 아니라 확인» 을 세웠고, 그 부산물로 공격 방향(ag)과
딜러별 체결이 생겼다. 그 둘이 있어야만 잴 수 있던 지표가 셋이다:

  R1  유효 스프레드   체결이 그 순간의 mid 에서 얼마나 떨어져 났나(bp). 호가 스프레드와 견준다.
                     + 최우선 체결률 — 「최우선이 실제로 맞는 자리인가」(v12 가 37% 로 보고한 수).
  R2  불균형 → 공격   체결 직전 책의 딜러 수 불균형(비드−오퍼)이 «누가 쳤나» 를 예측하는가.
                     ★기계적 편향 제거: 맞은 호가 자신을 빼고, 양면이 다 선 책만 센다.
                     위약 = 같은 (날, 종목) 안에서 공격 방향을 뒤섞음.
  R2b 불균형 → mid    호가 사건마다 불균형과 15분 뒤 mid 변화(금리). 비드가 많으면 금리가 내려가야 한다.
  R3  딜러 경쟁→점유  Hendershott 2025 재현 — «좋은 호가를 많이 내는 딜러가 주문흐름을 가져간다».
                     딜러-일 패널: 호가 수·최우선 게시 비율·귀속 체결 수.
                     위약 = 그날 체결을 호가 수에 비례해 무작위 재배정 → 「품질」효과가 사라져야 한다.
  R4  호가/체결       종목-일 quote-to-trade.

책 접기 규약은 라이브(kbond_live.py)와 같다 — 키 (딜러, 방향, 종목) 절대값 교체 · TTL 1800초 ·
uncross(크로스 쌍 중 오래된 쪽 제거) · 오퍼 최우선 = 오퍼 중 최고 금리, 비드 최우선 = 비드 중 최저 금리 ·
귀속 = 같은 종목 · 레벨 일치 · 같은 브로커 우선 · 30분 창 · 수량 없음 = 100억.

★시각축 — v12 가 두 번 데인 자리. 초는 secs() 한 곳에서만 만들고 장중인지 assert 한다.

  python kbond_dyn_study.py [--since 2024-02-14] [--out C:\\...\\kbond_dyn_study.json]
"""
import argparse
import json
import sys
import time
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

BASE = r"C:\Users\infomax\Projects\data\kbond"
TTL = 1800
FILL_WIN = 1800
DFLT_AMT = 100.0          # [OWNER 2026-09-03] 수량 표기 없음 = 100억
H = 900                   # R2b 지평(초)


def secs(s):
    """datetime64 → 초. 해상도가 us 로 와도 ns 로 맞춘 뒤 나눈다(v12 T 함정)."""
    return s.astype("datetime64[ns]").astype("int64").to_numpy() / 1e9


def uncross(asks, bids):
    """라이브 uncross_best 와 같은 규약으로 «살아남는 집합» 을 돌려준다.
    ★[OWNER 2026-09-15] 락(간격 0)은 안 걷는다 — 불변식은 «오퍼 <= 비드».
    """
    asks = list(asks)
    bids = list(bids)
    for _ in range(200):
        if not asks or not bids:
            break
        ba = max(asks, key=lambda e: (e["y"], e["t"]))
        bb = min(bids, key=lambda e: (e["y"], -e["t"]))
        if ba["y"] <= bb["y"]:
            break
        if ba["t"] <= bb["t"]:
            asks = [e for e in asks if e is not ba]
        else:
            bids = [e for e in bids if e is not bb]
    return asks, bids


def best_of(asks, bids):
    fa = max(asks, key=lambda e: (e["y"], e["t"])) if asks else None
    fb = min(bids, key=lambda e: (e["y"], -e["t"])) if bids else None
    return fa, fb


def auc(score, label):
    """Mann-Whitney AUC. label 1 이 score 가 클수록 그렇다고 예측하는 방향."""
    score = np.asarray(score, float)
    label = np.asarray(label, bool)
    n1, n0 = label.sum(), (~label).sum()
    if n1 == 0 or n0 == 0:
        return np.nan
    r = pd.Series(score).rank().to_numpy()
    return (r[label].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2024-02-14")
    ap.add_argument("--out", default=BASE + r"\kbond_dyn_study.json")
    ap.add_argument("--perm", type=int, default=20)
    a = ap.parse_args()
    t0 = time.time()
    rng = np.random.default_rng(20260915)

    # ── 적재 ───────────────────────────────────────────────────────────────
    QC = ["Date", "Timestamp", "Room", "BondCode", "MsgType", "Position", "QuoteYield",
          "AmountEff", "BrokerKey", "Message"]
    q = pd.read_parquet(BASE + r"\kbond_structured_data.parquet", columns=QC,
                        filters=[("Sector", "==", "국고")])
    q = q[(q.MsgType == "QUOTE") & q.BondCode.notna() & q.Position.isin(["BUY", "SELL"])
          & q.QuoteYield.notna() & q.BrokerKey.notna() & (q.Date >= a.since)].copy()
    # 방을 가로지르는 같은 문장(20초) — 국고는 한 방이 99% 라 거의 없다. 세는 지표만 위해 걷는다.
    q["ts"] = secs(q.Timestamp)
    q["b20"] = (q.ts // 20).astype(int)
    before = len(q)
    q = q.sort_values("ts").drop_duplicates(["BrokerKey", "Message", "b20"], keep="first")
    n_dup = before - len(q)
    q["d"] = secs(q.Date)
    assert 8 * 3600 < np.median(q.ts - q.d) < 20 * 3600, "호가 시각이 장중이 아니다 — 시각축을 의심"

    f = pd.read_parquet(BASE + r"\kbond_fills.parquet")
    f = f[(f.Sector == "국고") & f.BondCode.notna() & f.QuoteYield.notna()
          & (f.RepostSeq.fillna(0) == 0) & (f.DupSeq.fillna(0) == 0) & (f.Date >= a.since)].copy()
    f["ts"] = secs(f.Timestamp)
    f["d"] = secs(f.Date)
    assert 8 * 3600 < np.median(f.ts - f.d) < 20 * 3600, "체결 시각이 장중이 아니다 — 시각축을 의심"
    # 브로커 키: 체결표엔 BrokerKey 가 없고 Broker(서명 원문)만 있다. 본표의 BrokerKey 는
    # parse_kbond_logs.broker_key(전화번호 정규화)라 «같은 함수» 를 체결표에 지나게 한다.
    # (첫 판은 서명 앞부분을 키로 써서 겹침 0% — 딜러+레벨 귀속이 통째로 0 이 됐었다.)
    sys.path.insert(0, str(Path(__file__).parent))
    from parse_kbond_logs import broker_key
    f["bk"] = f.Broker.map(lambda s: str(broker_key(s) or "")[:14] if isinstance(s, str) else "")
    q["bk"] = q.BrokerKey.map(lambda s: str(s)[:14])
    f = f[f.bk != ""]
    # 본표 BrokerKey 가 체결표 Broker 와 같은 꼴인지 — 겹치는 키 비율로 확인한다.
    ov = len(set(f.bk) & set(q.bk)) / max(1, f.bk.nunique())
    print(f"적재 {time.time()-t0:.0f}s — 호가 {len(q):,}(중복 제거 {n_dup:,}) · 체결 {len(f):,} · "
          f"날 {q.Date.nunique()} · 브로커 키 겹침 {ov:.1%}")
    if ov < 0.5:
        # 체결표 Broker 원문과 본표 BrokerKey 의 꼴이 다르면 «같은 브로커» 판정이 죽는다.
        print("  ★브로커 키가 안 맞물린다. 예:", f.Broker.head(3).tolist(), q.BrokerKey.head(3).tolist())

    # ── 종목-일 루프 ────────────────────────────────────────────────────────
    q = q.sort_values(["Date", "BondCode", "ts"])
    f = f.sort_values(["Date", "BondCode", "ts"])
    fg = {k: g for k, g in f.groupby(["Date", "BondCode"], sort=False)}

    fills_out = []          # 체결마다 한 줄
    path_out = []           # R2b: 호가 사건마다 (그룹id, t, imb, mid)
    dealer_day = defaultdict(lambda: [0, 0, 0, 0])   # (date, bk) -> [q, at_best_post, f_own, f_any_level]
    qt = []                 # (date, code, n_q, n_f)
    gid = 0
    for (date, code), g in q.groupby(["Date", "BondCode"], sort=False):
        gid += 1
        fl = fg.get((date, code))
        ev = [(t, 0, i) for i, t in enumerate(g.ts.to_numpy())]
        if fl is not None:
            ev += [(t, 1, i) for i, t in enumerate(fl.ts.to_numpy())]
        ev.sort()
        book = {}
        gb, gs, gy, ga = (g.bk.to_numpy(), g.Position.to_numpy(), g.QuoteYield.to_numpy(float),
                          g.AmountEff.to_numpy(float))
        if fl is not None:
            fb_, fy, fpos, fidx = (fl.bk.to_numpy(), fl.QuoteYield.to_numpy(float),
                                   fl.Position.to_numpy(), fl.index.to_numpy())
        n_q = len(g)
        n_f_att = 0
        for t, kind, i in ev:
            # 살아 있는 것만 남긴다(TTL) — 같은 키의 절대값 교체는 dict 가 한다
            if kind == 0:
                side = "S" if gs[i] == "SELL" else "B"
                alive = [e for e in book.values() if t - e["t"] <= TTL]
                asks, bids = uncross([e for e in alive if e["s"] == "S"],
                                     [e for e in alive if e["s"] == "B"])
                fa, fb = best_of(asks, bids)
                y = float(gy[i])
                # 게시 순간 «최우선 이상» 이었나 (오퍼는 높을수록·비드는 낮을수록 공격적)
                if side == "S":
                    at = fa is None or y >= fa["y"] - 1e-9
                else:
                    at = fb is None or y <= fb["y"] + 1e-9
                key = (gb[i], side)
                book[key] = {"t": t, "s": side, "y": y, "k": gb[i],
                             "a": (float(ga[i]) if not np.isnan(ga[i]) else DFLT_AMT)}
                dd = dealer_day[(date, gb[i])]
                dd[0] += 1
                dd[1] += int(at)
                # R2b 경로: 새 호가를 넣은 뒤의 책
                alive = [e for e in book.values() if t - e["t"] <= TTL]
                asks, bids = uncross([e for e in alive if e["s"] == "S"],
                                     [e for e in alive if e["s"] == "B"])
                if asks and bids:
                    fa, fb = best_of(asks, bids)
                    nb, na = len(bids), len(asks)
                    path_out.append((gid, t, (nb - na) / (nb + na), (fa["y"] + fb["y"]) / 2))
                continue
            # 체결
            y = float(fy[i])
            cand = [e for e in book.values() if e["t"] <= t and t - e["t"] <= FILL_WIN
                    and abs(e["y"] - y) <= 1e-9]
            own = [e for e in cand if e["k"] == fb_[i]]
            other = [e for e in cand if e["k"] != fb_[i]]
            hit = (max(own, key=lambda e: e["t"]) if own
                   else (max(other, key=lambda e: e["t"]) if other else None))
            # ★잠금 동점 — 같은 레벨에 오퍼와 비드가 다 서 있는데 자기 호가가 없으면 «최신 것» 을
            #   고르는 라이브 규칙은 방향을 사실상 동전 던지기로 정한다. 그런 귀속은 표시하고
            #   R2 에서 뺀다(안 빼면 «사람이 많은 쪽이 최신일 확률이 높다» 는 기계적 편향이 든다).
            amb = (not own) and bool(other) and len({e["s"] for e in other}) > 1
            alive = [e for e in book.values() if e["t"] <= t and t - e["t"] <= TTL]
            asks, bids = uncross([e for e in alive if e["s"] == "S"],
                                 [e for e in alive if e["s"] == "B"])
            fa, fb = best_of(asks, bids)
            row = {"fi": int(fidx[i]), "date": str(date)[:10], "code": code, "t": t, "y": y,
                   "pos": fpos[i], "hit": hit is not None, "amb": amb,
                   "own": bool(own), "ag": None, "ab": None, "eff": None, "qs": None,
                   "imb": None, "imb_a": None, "two": False, "hit_age": None, "best_age": None,
                   "dist": None, "cross_hit": False}
            if fa is not None and fb is not None:
                row["qs"] = (fb["y"] - fa["y"]) * 100
                row["mid"] = (fa["y"] + fb["y"]) / 2
            if hit is not None:
                n_f_att += 1
                ag = "B" if hit["s"] == "S" else "S"
                row["ag"] = ag
                dd = dealer_day[(date, hit["k"])]
                dd[3] += 1
                if own:
                    dd[2] += 1
                surv = asks if hit["s"] == "S" else bids
                in_surv = any(e is hit for e in surv)
                row["cross_hit"] = not in_surv
                bst = fa if hit["s"] == "S" else fb
                if bst is not None:
                    row["ab"] = abs(bst["y"] - hit["y"]) <= 1e-9
                    row["dist"] = abs(bst["y"] - hit["y"]) * 100
                    row["best_age"] = t - bst["t"]
                row["hit_age"] = t - hit["t"]
                if fa is not None and fb is not None:
                    mid = (fa["y"] + fb["y"]) / 2
                    # 사 간 체결(오퍼 맞음)의 비용 = mid − 오퍼금리 (금리가 낮을수록 비싸다)
                    row["eff"] = ((mid - y) if ag == "B" else (y - mid)) * 100
                # 불균형 — 맞은 호가 자신은 뺀다(안 빼면 «오퍼가 있으니 오퍼가 맞았다» 항등식)
                a2 = [e for e in asks if e is not hit]
                b2 = [e for e in bids if e is not hit]
                if a2 and b2:
                    row["two"] = True
                    row["imb"] = (len(b2) - len(a2)) / (len(b2) + len(a2))
                    da, db = sum(e["a"] for e in a2), sum(e["a"] for e in b2)
                    row["imb_a"] = (db - da) / (db + da) if (da + db) > 0 else None
            fills_out.append(row)
        qt.append((str(date)[:10], code, n_q, 0 if fl is None else len(fl), n_f_att))
    print(f"접기 {time.time()-t0:.0f}s — 종목-일 {gid:,} · 체결 행 {len(fills_out):,} · "
          f"경로 점 {len(path_out):,} · 딜러-일 {len(dealer_day):,}")

    F = pd.DataFrame(fills_out)
    R = {"n_quotes": int(len(q)), "n_fills": int(len(F)), "n_days": int(q.Date.nunique()),
         "since": a.since, "n_dup_dropped": int(n_dup)}

    # ── R0 귀속 재현 (v12 와 같은 수가 나와야 한다) ─────────────────────────
    att = F[F.hit]
    pc = att[att.pos.isin(["BUY", "SELL"])]
    # 문면 «팔자» 체결 = 오퍼가 맞았다 = 사 감(B). v12 의 규약(s != ag) 그대로.
    pc_ok = ((pc.pos == "SELL") == (pc.ag == "B")).mean() if len(pc) else np.nan
    pc_na = pc[~pc.amb]
    pc_ok_na = ((pc_na.pos == "SELL") == (pc_na.ag == "B")).mean() if len(pc_na) else np.nan
    R["R0"] = {"attributed_pct": float(F.hit.mean() * 100), "own_pct": float(F.own.mean() * 100),
               "amb_pct_of_att": float(att.amb.mean() * 100),
               "pos_ctrl_pct": float(pc_ok * 100), "pos_ctrl_n": int(len(pc)),
               "pos_ctrl_pct_unamb": float(pc_ok_na * 100), "pos_ctrl_n_unamb": int(len(pc_na)),
               "ag_B": int((att.ag == "B").sum()), "ag_S": int((att.ag == "S").sum())}
    print(f"\n[R0] 귀속 {R['R0']['attributed_pct']:.1f}% (딜러+레벨 {R['R0']['own_pct']:.1f}% · 잠금 동점 {R['R0']['amb_pct_of_att']:.1f}%) · "
          f"양성대조(문면 방향) {pc_ok:.1%} n={len(pc):,} · 동점 빼면 {pc_ok_na:.1%} n={len(pc_na):,}"
          f" · 사 감 {R['R0']['ag_B']:,} 팜 {R['R0']['ag_S']:,}")

    # ── R1 유효 스프레드 · 최우선 체결률 ────────────────────────────────────
    e1 = att[att.eff.notna()]
    qs_all = F[F.qs.notna()].qs
    ab = att[att.ab.notna()]
    def q_(s, p):
        return float(np.percentile(s, p)) if len(s) else None
    R["R1"] = {
        "n_eff": int(len(e1)), "eff_med": q_(e1.eff, 50), "eff_p25": q_(e1.eff, 25), "eff_p75": q_(e1.eff, 75),
        "eff_neg_pct": float((e1.eff < -1e-9).mean() * 100) if len(e1) else None,
        "qs_med_at_fill": q_(qs_all, 50), "qs_half_med": q_(qs_all / 2, 50),
        "at_best_pct": float(ab.ab.mean() * 100) if len(ab) else None, "n_ab": int(len(ab)),
        "cross_hit_pct": float(att.cross_hit.mean() * 100),
        "behind_dist_med_bp": q_(ab[~ab.ab.astype(bool)].dist, 50),
        "behind_best_age_med": q_(ab[~ab.ab.astype(bool)].best_age, 50),
        "behind_hit_age_med": q_(ab[~ab.ab.astype(bool)].hit_age, 50),
        "atbest_best_age_med": q_(ab[ab.ab.astype(bool)].hit_age, 50),
        "eff_by_ab": {str(k): {"n": int(len(v)), "med": q_(v.eff, 50)}
                      for k, v in e1[e1.ab.notna()].groupby("ab")},
    }
    def share(s, edges):
        s = np.asarray(s, float)
        out = {}
        for lo, hi, nm in edges:
            out[nm] = float(((s >= lo) & (s < hi)).mean() * 100) if len(s) else None
        return out
    R["R1"]["qs_dist"] = share(qs_all, [(-99, 0.25, "0(잠금)"), (0.25, 0.75, "0.5"), (0.75, 1.25, "1.0"), (1.25, 99, "1.5+")])
    R["R1"]["eff_dist"] = share(e1.eff, [(-99, -0.01, "음수"), (-0.01, 0.01, "0"), (0.01, 0.3, "0.25"), (0.3, 0.6, "0.5"), (0.6, 99, "0.75+")])
    R["R1"]["eff_mean"] = float(e1.eff.mean()) if len(e1) else None
    R["R1"]["qs_mean_at_fill"] = float(qs_all.mean()) if len(qs_all) else None
    r1 = R["R1"]
    print(f"     체결 시점 호가 스프레드 분포 % {r1['qs_dist']} · 평균 {r1['qs_mean_at_fill']:.3f}bp")
    print(f"     유효 반스프레드 분포 % {r1['eff_dist']} · 평균 {r1['eff_mean']:.3f}bp")
    print(f"\n[R1] 유효 반스프레드 중앙 {r1['eff_med']:.2f}bp [{r1['eff_p25']:.2f}, {r1['eff_p75']:.2f}] n={r1['n_eff']:,}"
          f" · 호가 반스프레드 중앙 {r1['qs_half_med']:.2f}bp · 음수(mid 안쪽에서 남) {r1['eff_neg_pct']:.1f}%")
    print(f"     최우선 체결률 {r1['at_best_pct']:.1f}% (n={r1['n_ab']:,}) · 크로스로 걷힌 호가가 맞음 {r1['cross_hit_pct']:.1f}%")
    print(f"     최우선 뒤에서 맞은 체결: 최우선과 거리 중앙 {r1['behind_dist_med_bp']}bp · "
          f"그때 최우선 나이 중앙 {r1['behind_best_age_med']}s vs 맞은 호가 나이 {r1['behind_hit_age_med']}s"
          f" · 최우선에서 맞은 호가 나이 {r1['atbest_best_age_med']}s")
    print(f"     유효 by 최우선 여부: {r1['eff_by_ab']}")
    # 시간대별 호가 스프레드(체결 시점 기준)
    hod = F[F.qs.notna()].copy()
    hod["h"] = ((hod.t - secs(pd.to_datetime(hod.date))) // 3600).astype(int)
    R["R1"]["qs_by_hour"] = {int(k): {"n": int(len(v)), "med": q_(v.qs, 50)} for k, v in hod.groupby("h") if 8 <= k <= 16}
    print("     체결 시점 호가 스프레드(bp) 시간대별:", {k: round(v["med"], 2) for k, v in R["R1"]["qs_by_hour"].items()})

    # ── R2 불균형 → 공격 방향 ──────────────────────────────────────────────
    two = att[att.two & att.imb.notna() & ~att.amb].copy()
    lab = (two.ag == "B").to_numpy()
    two["imb_w"] = two.imb - two.groupby(["date", "code"]).imb.transform("mean")
    A_w = auc(two.imb_w, lab)
    A = auc(two.imb, lab)
    A_amt = auc(two.imb_a.fillna(0), lab)
    perms = []
    for _ in range(a.perm):
        sh = two.groupby(["date", "code"]).ag.transform(lambda s: s.sample(frac=1, random_state=int(rng.integers(1 << 30))).to_numpy())
        perms.append(auc(two.imb, (sh == "B").to_numpy()))
    two["qn"] = pd.cut(two.imb, [-1.01, -0.5, -0.15, 0.15, 0.5, 1.01],
                       labels=["오퍼 우세", "오퍼 약우세", "균형", "비드 약우세", "비드 우세"])
    by = two.groupby("qn", observed=True).agg(n=("ag", "size"), pB=("ag", lambda s: (s == "B").mean() * 100))
    # 「자기 자신 빼기」를 안 했으면 어땠나 — 항등식의 크기를 같이 보인다
    R["R2"] = {"n": int(len(two)), "auc_n": float(A), "auc_amt": float(A_amt), "auc_within": float(A_w),
               "perm_auc_mean": float(np.mean(perms)), "perm_auc_sd": float(np.std(perms)),
               "perm_auc_max": float(np.max(perms)),
               "pB_base": float(lab.mean() * 100),
               "by_imb": {str(k): {"n": int(v.n), "pB": float(v.pB)} for k, v in by.iterrows()}}
    # 딜러+레벨(own) 귀속만으로도 같은가 (레벨만 귀속은 공격자 판정이 약하다)
    tw_own = two[two.own]
    R["R2"]["auc_own_only"] = float(auc(tw_own.imb, (tw_own.ag == "B").to_numpy()))
    R["R2"]["n_own"] = int(len(tw_own))
    print(f"\n[R2] 불균형→공격 방향 AUC {A:.3f} (딜러 수) · {A_amt:.3f} (수량) · 그룹내 {A_w:.3f} · own 만 {R['R2']['auc_own_only']:.3f} n={len(two):,}"
          f" · 위약 {np.mean(perms):.3f}±{np.std(perms):.3f} (max {np.max(perms):.3f}) · 기저 P(사 감) {lab.mean():.1%}")
    print("     불균형 구간별 P(사 감):", {k: (v["n"], round(v["pB"], 1)) for k, v in R["R2"]["by_imb"].items()})

    # ── R2b 불균형 → 15분 뒤 mid ──────────────────────────────────────────
    P = pd.DataFrame(path_out, columns=["g", "t", "imb", "mid"])
    P = P.sort_values(["g", "t"]).reset_index(drop=True)
    # 같은 그룹 안에서 t+H 이하 마지막 점의 mid
    out_d = np.full(len(P), np.nan)
    for g, idx in P.groupby("g").indices.items():
        tt = P.t.to_numpy()[idx]
        mm = P.mid.to_numpy()[idx]
        j = np.searchsorted(tt, tt + H, side="right") - 1
        ok = j > np.arange(len(idx))          # 뒤에 점이 하나라도 있어야 «변화» 다
        out_d[idx[ok]] = (mm[j[ok]] - mm[ok]) * 100
    P["dmid"] = out_d
    P2 = P[P.dmid.notna() & (P.imb.abs() > 0)].copy()
    rho = P2[["imb", "dmid"]].corr(method="spearman").iloc[0, 1]
    # 그룹내: 순위를 (종목,일) 안에서 매기고 그룹 평균을 뺀 뒤 Pearson = 그룹내 Spearman(가중)
    def within_rho(x, y, g):
        rx = x.groupby(g).rank()
        ry = y.groupby(g).rank()
        rx = rx - rx.groupby(g).transform("mean")
        ry = ry - ry.groupby(g).transform("mean")
        return float(np.corrcoef(rx.to_numpy(), ry.to_numpy())[0, 1])
    rho_w = within_rho(P2.imb, P2.dmid, P2.g)
    gm = P2.groupby("g").agg(imb=("imb", "mean"), dmid=("dmid", "mean"), n=("dmid", "size"))
    gm = gm[gm.n >= 30]
    rho_between = float(gm[["imb", "dmid"]].corr(method="spearman").iloc[0, 1])
    P2 = P2.assign(qn=pd.cut(P2.imb, [-1.01, -0.5, -0.15, 0.15, 0.5, 1.01],
                             labels=["오퍼 우세", "오퍼 약우세", "균형", "비드 약우세", "비드 우세"]))
    by2 = P2.groupby("qn", observed=True).agg(n=("dmid", "size"), dn=("dmid", lambda s: (s < 0).mean() * 100),
                                             up=("dmid", lambda s: (s > 0).mean() * 100), med=("dmid", "median"))
    perm2 = []
    for _ in range(min(a.perm, 10)):
        sh = P2.groupby("g").imb.transform(lambda s: s.sample(frac=1, random_state=int(rng.integers(1 << 30))).to_numpy())
        perm2.append(within_rho(sh, P2.dmid, P2.g))
    R["R2b"] = {"n": int(len(P2)), "rho_pooled": float(rho), "rho_within": rho_w, "rho_between_groups": rho_between,
                "n_groups_between": int(len(gm)),
                "perm_within_mean": float(np.mean(perm2)), "perm_within_sd": float(np.std(perm2)), "H": H,
                "by_imb": {str(k): {"n": int(v.n), "down": float(v.dn), "up": float(v.up), "med": float(v.med)}
                           for k, v in by2.iterrows()}}
    print(f"\n[R2b] 불균형→{H//60}분 뒤 mid 변화 — 그룹내 Spearman {rho_w:+.3f} (위약 {np.mean(perm2):+.3f}±{np.std(perm2):.3f}) · "
          f"풀링 {rho:+.3f} · 그룹간(종목-일 평균, n≥30 {len(gm):,}) {rho_between:+.3f} · n={len(P2):,}")
    print("      구간별 (n, 금리↓%, 금리↑%, 중앙bp):", {k: (v["n"], round(v["down"], 1), round(v["up"], 1), round(v["med"], 2))
                                                       for k, v in R["R2b"]["by_imb"].items()})

    # ── R3 딜러 경쟁 → 체결 점유 (Hendershott) ────────────────────────────
    D = pd.DataFrame([(d, k, v[0], v[1], v[2], v[3]) for (d, k), v in dealer_day.items()],
                     columns=["date", "k", "q", "abp", "f_own", "f_any"])
    D = D[D.q >= 5].copy()
    D["ab_frac"] = D.abp / D.q
    D["fpq"] = D.f_own / D.q
    # 그날 안에서 호가 수 점유 ↔ 체결 점유
    D["qs_"] = D.q / D.groupby("date").q.transform("sum")
    D["fs_"] = D.f_own / D.groupby("date").f_own.transform("sum").replace(0, np.nan)
    rho_share = D[D.fs_.notna()][["qs_", "fs_"]].corr(method="spearman").iloc[0, 1]
    # 품질(최우선 게시 비율) 3분위 — 그날 안에서 나눈다
    D["abt"] = D.groupby("date").ab_frac.transform(
        lambda s: pd.qcut(s.rank(method="first"), 3, labels=["하", "중", "상"]) if len(s) >= 6 else pd.Series([None] * len(s), index=s.index))
    real = D[D.abt.notna()].groupby("abt", observed=True).agg(n=("k", "size"), q=("q", "sum"), f=("f_own", "sum"))
    real["fpq"] = real.f / real.q
    # 위약: 그날 own 체결 총수를 호가 수 비례로 다시 뿌린다
    pl = []
    for _ in range(a.perm):
        Fp = np.zeros(len(D))
        for d, idx in D.groupby("date").indices.items():
            tot = int(D.f_own.to_numpy()[idx].sum())
            if tot == 0:
                continue
            p = D.q.to_numpy()[idx].astype(float)
            Fp[idx] = rng.multinomial(tot, p / p.sum())
        Dp = D.assign(fp=Fp)
        r = Dp[Dp.abt.notna()].groupby("abt", observed=True).agg(q=("q", "sum"), f=("fp", "sum"))
        pl.append((r.f / r.q).to_dict())
    pl = pd.DataFrame(pl)
    # 로그 회귀: log(1+f) ~ log(1+q) + ab_frac  (날짜 평균 제거)
    Z = D.copy()
    Z["lf"] = np.log1p(Z.f_own)
    Z["lq"] = np.log1p(Z.q)
    for c in ("lf", "lq", "ab_frac"):
        Z[c] = Z[c] - Z.groupby("date")[c].transform("mean")
    X = np.column_stack([Z.lq, Z.ab_frac])
    beta, *_ = np.linalg.lstsq(X, Z.lf.to_numpy(), rcond=None)
    res = Z.lf.to_numpy() - X @ beta
    dof = len(Z) - 2
    se = np.sqrt(np.diag(np.linalg.inv(X.T @ X)) * (res @ res) / dof)
    R["R3"] = {"n_dealer_day": int(len(D)), "rho_share": float(rho_share),
               "fpq_by_quality": {str(k): {"n": int(v.n), "q": int(v.q), "f": int(v.f), "fpq": float(v.fpq)}
                                  for k, v in real.iterrows()},
               "placebo_fpq_by_quality": {c: {"mean": float(pl[c].mean()), "sd": float(pl[c].std())} for c in pl.columns},
               "beta_lq": float(beta[0]), "se_lq": float(se[0]), "beta_ab": float(beta[1]), "se_ab": float(se[1])}
    print(f"\n[R3] 딜러-일 {len(D):,} · 호가 점유↔체결 점유 Spearman {rho_share:+.3f}")
    print("     최우선 게시 비율 3분위별 체결/호가:",
          {k: (v["n"], round(v["fpq"], 4)) for k, v in R["R3"]["fpq_by_quality"].items()},
          "· 위약:", {k: round(v["mean"], 4) for k, v in R["R3"]["placebo_fpq_by_quality"].items()})
    print(f"     log(1+f) ~ {beta[0]:.3f}(±{se[0]:.3f})·log(1+q) + {beta[1]:.3f}(±{se[1]:.3f})·최우선비율  [날짜 FE]")

    # ── R4 호가/체결 ───────────────────────────────────────────────────────
    QT = pd.DataFrame(qt, columns=["date", "code", "n_q", "n_f", "n_att"])
    tot_q, tot_f = QT.n_q.sum(), QT.n_f.sum()
    act = QT[QT.n_f > 0]
    R["R4"] = {"q_per_fill_total": float(tot_q / max(1, tot_f)),
               "q_per_fill_med_inst_day": float((act.n_q / act.n_f).median()),
               "inst_days_with_fill_pct": float((QT.n_f > 0).mean() * 100),
               "fill_share_top_decile_inst_day": float(QT.sort_values("n_q").tail(len(QT) // 10).n_f.sum() / max(1, tot_f) * 100)}
    print(f"\n[R4] 호가/체결 전체 {R['R4']['q_per_fill_total']:.1f} · 체결 있는 종목-일 중앙 {R['R4']['q_per_fill_med_inst_day']:.1f}"
          f" · 체결 있는 종목-일 {R['R4']['inst_days_with_fill_pct']:.1f}% · 호가 상위 10% 종목-일이 체결의 {R['R4']['fill_share_top_decile_inst_day']:.1f}%")

    R["elapsed_s"] = time.time() - t0
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(R, fh, ensure_ascii=False, indent=1, default=str)
    F.to_parquet(a.out.replace(".json", "_fills.parquet"), index=False)
    print(f"\n저장 {a.out} · {R['elapsed_s']:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
