# -*- coding: utf-8 -*-
"""검정층 — 문면 은어를 «민평 검정» 으로 표제어에 붙인다 [OWNER 2026-09-09].

## 칸을 무엇으로 잡는가 — 회차가 가르는 정보다

2026-09-09 실측. 하드 음성 11쌍(사람이 아는 «확실히 다른» 발행체)으로 잣대 둘을
대조했다. 양성은 둘 다 100% 통과한다. 갈리는 건 음성이다.

    칸 = (날짜, 만기)            음성 오통과 3/11
        국민은행 ~ 신한은행  n=178 중앙 0.10bp   <- 접힌다
        신한은행 ~ 우리은행  n=149 중앙 0.10bp   <- 접힌다
        삼성카드 ~ 신한카드  n= 35 중앙 0.10bp   <- 접힌다
    칸 = (날짜, 만기, 끝전)       음성 오통과 3/11
        산금 ~ 중금        n= 33 중앙 0.00bp   <- 산업은행과 기업은행이 접힌다
    칸 = (날짜, 회차, 만기)       음성 오통과 **0/11**
        9쌍은 같은 칸에 아예 안 만난다 · 2쌍은 n=1 (문턱 미만)

AAA 은행채는 같은 커브로 매겨져서 «만기만» 으로는 원래 안 갈린다. 표본을 키울수록
나빠진다 — n>=40 에서 음성 오통과가 100% 였다(큰 n 이 곧 큰 AAA). 끝전을 넣어도
안 산다. 가르는 건 **회차**뿐이다.

## 그래서 이 층이 못 하는 일

회차를 안 달고 다니는 은어(한전·농중·도공·예특·외평·중금·수금)는 이 검정으로
**못 붙인다.** 그건 owner 층으로 간다. 이 층은 회차를 달고 다니는 것만 맡는다.

## 표제어끼리도 붙인다 — 음차형이 둘씩 산다

원장 자체가 «SK하이닉스» 와 «에스케이하이닉스» 를 따로 싣는다. 같은 검정을 표제어
쌍에도 걸어 통과한 것을 병합한다. 하드 음성 11쌍이 이 칸에서 0/11 이었으므로
같은 위험도다 — 발전 5사도 같은 칸에 아예 안 만난다(n=0).

산출: kbond_issuer_derived.json
      {"variants": {이형태: {"canon":…, "n":…, "med_bp":…}},
       "merges":   [[버릴 표제어, 남길 표제어, n, bp], …]}
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

import kbond_issuer_dict as KD

HERE = Path(__file__).parent
OUT = HERE / "kbond_issuer_derived.json"
CACHE = HERE / "artifacts" / "cr_heads.parquet"

RE_SER = re.compile(r"(\d{1,4}-\d{1,3})$")
N_MIN = 5          # 칸 수 문턱. 실측에서 하드 음성이 n=1 로만 만나 5 면 넉넉하다.
BP_MAX = 1.0       # 중앙 |Δ민평| 문턱 (bp). 101쌍 별칭표와 같은 값.
MARGIN = 3.0       # 2위 후보가 이만큼 나빠야 «갈렸다» 고 본다.


def variant_map(d):
    """앵커 = «원장이 아는 이름» + «사람이 판정한 이름».

    ⚠ 앞선 실행의 산출(kbond_issuer_derived.json)은 **일부러 안 쓴다.** 쓰면 이번
      유도가 지난 유도를 근거로 삼아 되먹임이 생기고, 다시 돌릴 때마다 답이 달라진다.
    """
    import kbond_issuer as KI                # OWNER 표만 빌린다(파생층은 안 쓴다)
    v = {}
    for canon, e in d.items():
        v[KD.norm(canon)] = canon
        for x in e["variants"]:
            v.setdefault(KD.norm(x), canon)
    for k, tgt in KI.OWNER.items():
        # owner 가 가리킨 곳이 사전에 있으면 그 표제어로, 없으면 문자열 그대로.
        v.setdefault(KD.norm(k), v.get(KD.norm(tgt), tgt))
    return v


def split(raw):
    """'산은캐피탈725-2' -> ('산은캐피탈', '725-2')"""
    s = str(raw).strip()
    m = RE_SER.search(s)
    return (s[:m.start()].strip(), m.group(1)) if m else (s, None)


def build_cache(out=CACHE):
    """검정에 쓸 캐시를 원장에서 굽는다 — [문면 원문 머리말, 날짜, 만기, 민평].

    ⚠ 이 파일은 `*.parquet` 이라 git 에 안 올라간다. 새 클론에서 유도를 돌리려면
      여기서 다시 구워야 한다. `issuer_guess` 는 `kbond_issuer` 것을 쓴다 —
      원장·화면·검정이 같은 추정기를 봐야 한다(따로 두면 검정이 자기 구현을 검증한다).
    """
    import pyarrow.parquet as pq

    import kbond_issuer as KI
    src = r"C:\Users\infomax\Projects\data\kbond\kbond_structured_data.parquet"
    f = pq.ParquetFile(src)
    rows = []

    def nn(x):
        return None if x is None or (isinstance(x, float) and pd.isna(x)) or str(x) == "nan" \
            else str(x)

    for i in range(f.metadata.num_row_groups):
        t = f.read_row_group(i, columns=["Date", "BondName", "Message", "Sector",
                                         "Maturity", "MPYield"]).to_pandas()
        t = t[t["Sector"].astype("string") == "크레딧/기타"]
        for dt, bn, msg, mat, mp in zip(t["Date"], t["BondName"], t["Message"],
                                        t["Maturity"], t["MPYield"]):
            raw = nn(bn) or KI.issuer_of(nn(msg) or "")
            if raw:
                rows.append((str(dt)[:10], raw[:20], nn(mat),
                             float(mp) if pd.notna(mp) else None))
    df = pd.DataFrame(rows, columns=["d", "raw", "mat", "mp"])
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False, compression="zstd")
    print(f"캐시 {len(df):,}행 · 원문 머리말 {df.raw.nunique():,}종 -> {out}")
    return df


def derive(cache=CACHE, dic=None):
    d = dic if dic is not None else json.loads((HERE / "kbond_issuer_dict.json")
                                               .read_text(encoding="utf-8"))
    V = variant_map(d)
    df = pd.read_parquet(cache) if Path(cache).exists() else build_cache(Path(cache))
    df = df[df.mp.notna() & df.mat.notna()].copy()
    hs = df["raw"].map(split)
    df["head"] = [h for h, _ in hs]
    df["ser"] = [s for _, s in hs]
    df = df[df.ser.notna()]
    # ⚠ .map() 의 미매칭은 None 이 아니라 NaN 이고, str dtype 에서는 .where(...,None)
    #   으로도 안 돌아온다(다시 NaN 이 된다). object 로 내린 뒤 바꿔야 한다.
    _c = df["head"].map(KD.norm).map(V)
    df["canon"] = _c.astype(object).where(_c.notna(), None)

    g = (df.groupby(["d", "ser", "mat", "head"])
           .agg(mp=("mp", "median"), canon=("canon", "first")).reset_index())
    g["canon"] = g["canon"].astype(object).where(g["canon"].notna(), None)
    acc = defaultdict(list)                      # (문면 머리말, 표제어) -> [Δbp]
    for _, sub in g.groupby(["d", "ser", "mat"]):
        if len(sub) < 2:
            continue
        rec = list(zip(sub["head"], sub["mp"], sub["canon"]))
        for h, m, c in rec:
            if c is not None:
                continue                          # 이미 아는 이름은 붙일 필요가 없다
            for h2, m2, c2 in rec:
                if c2 is None or h2 == h:
                    continue
                acc[(h, c2)].append(abs(m - m2) * 100)

    by_head = defaultdict(list)
    for (h, c), v in acc.items():
        if len(v) < N_MIN:
            continue
        by_head[h].append((float(pd.Series(v).median()), c, len(v)))

    # ── 표제어끼리의 병합. 같은 칸에서 «둘 다 아는» 쌍을 모은다.
    pair = defaultdict(list)
    for _, sub in g.groupby(["d", "ser", "mat"]):
        if len(sub) < 2:
            continue
        rec = [(c, m) for c, m in zip(sub["canon"], sub["mp"]) if c is not None]
        for i in range(len(rec)):
            for j in range(i + 1, len(rec)):
                if rec[i][0] == rec[j][0]:
                    continue
                k = tuple(sorted([rec[i][0], rec[j][0]]))
                pair[k].append(abs(rec[i][1] - rec[j][1]) * 100)
    merges = []
    for (a, b), v in pair.items():
        if len(v) < N_MIN:
            continue
        med = float(pd.Series(v).median())
        if med <= BP_MAX:
            # 남기는 쪽 — ★한쪽이 다른 쪽의 접두면 **긴 쪽**을 남긴다.
            #   짧은 쪽을 고르면 「한국항공우주산업」이 「한국항공우주」로 뒤집힌다(실측).
            #   그 밖에는 이형태를 더 많이 거느린 쪽, 같으면 짧은 쪽(화면이 16자다).
            if a.startswith(b) or b.startswith(a):
                keep, drop_ = (a, b) if len(a) > len(b) else (b, a)
            else:
                keep, drop_ = sorted([a, b],
                                     key=lambda x: (-len(d.get(x, {}).get("variants", [])),
                                                    len(x)))[0:2]
            merges.append([drop_, keep, len(v), round(med, 2)])

    out, drop = {}, []
    for h, cands in by_head.items():
        cands.sort()
        med, canon, n = cands[0]
        if med > BP_MAX:
            drop.append((h, "민평 어긋남", round(med, 2), n)); continue
        # ★2위 후보가 바짝 붙어 있으면 안 붙인다 — 검정이 «갈랐다» 고 말할 수 없다.
        if len(cands) > 1 and cands[1][0] - med < MARGIN:
            drop.append((h, f"모호({cands[1][1]})", round(cands[1][0], 2), n)); continue
        out[h] = {"canon": canon, "n": n, "med_bp": round(med, 2)}
    return out, drop, merges


if __name__ == "__main__":
    got, drop, merges = derive()
    OUT.write_text(json.dumps({"variants": got, "merges": merges},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"검정 통과 이형태 {len(got):,}종 · 탈락 {len(drop):,}종 "
          f"· 표제어 병합 {len(merges):,}쌍  -> {OUT}")
    print()
    print("== 표제어 병합 상위 20 ==")
    for a, b, n, bp in sorted(merges, key=lambda x: -x[2])[:20]:
        print(f"  n={n:5d} {bp:5.2f}bp  {a:22s} -> {b}")
    top = sorted(got.items(), key=lambda kv: -kv[1]["n"])[:25]
    print("\n== 붙은 것 상위 25 ==")
    for h, e in top:
        print(f"  n={e['n']:5d} {e['med_bp']:5.2f}bp  {h:22s} -> {e['canon']}")
    print("\n== 탈락 상위 15 ==")
    for h, why, v, n in sorted(drop, key=lambda x: -x[3])[:15]:
        print(f"  n={n:5d} {v:6.2f}  {h:22s}  {why}")
