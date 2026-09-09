# -*- coding: utf-8 -*-
"""근접층 — 데스크가 줄여 부르는 이름을 원장 표제어에 붙인다 [2026-09-09 3차].

## 무엇이 남았나

민평 검정(`kbond_issuer_derive`)은 **두 이름이 같은 칸에 나타나야** 붙일 수 있다.
그런데 데스크가 늘 줄임말만 쓰면 원장 이름이 문면에 아예 안 나와 칸이 안 생긴다.
실측으로 남은 것이 이 꼴이다:

    SK에코플랜트    ->  에스케이에코플랜트          (음차)
    LS일렉트릭      ->  엘에스일렉트릭             (음차)
    파주에너지       ->  파주에너지서비스            (접미 절단)
    오릭스캐피탈      ->  오릭스캐피탈코리아           (접미 절단)
    맥쿼리한국인프라    ->  맥쿼리한국인프라투융자회사       (접미 절단)
    충북개발공사음성    ->  충북개발공사              (접미 덧붙음)

## 왜 위험한가 — 이름 모양으로 접는 자리다

발전 5사가 가르쳐 준 그 자리다. 그래서 가드를 넷 건다.

    1. 후보가 **정확히 하나**   여럿이면 안 붙인다
    2. 길이 차이 6자 이내      «신보» -> 아무거나 가 되는 것을 막는다
    3. **방향이 다르면 잣대도 다르다** (아래)
    4. 민평 검정이 **반대하지 않을 것**  같은 칸에서 만난 적이 있는데 어긋나면 버린다

### 방향을 왜 가르나

    A. 문면이 **짧다** (데스크가 줄여 부른다)   파주에너지 -> 파주에너지서비스
       원장 이름이 문면 것으로 시작한다. 줄여 부르는 건 데스크의 습관이라 받는다.
    B. 문면이 **길다** (뒤에 뭐가 붙었다)      한화토탈에너지 + «서비스»
       이건 «같은 회사의 다른 표기» 일 수도, **아예 다른 회사** 일 수도 있다.
       실측으로 걸렸다 — 한화토탈에너지서비스는 한화토탈에너지스가 **아니다**
       (`test_issuer` 의 KEEP_DISTINCT 가 잡았다). 그래서 B 는 민평 검정이
       **확인해 줄 때만** 받는다(n>=1 · 중앙 <=1bp). 확인이 없으면 안 붙인다.

⚠ 처음에 «계열이 같을 것» 을 가드로 넣었다가 뺐다. 원문 줄임말은 정본이 아니라서
  `classify_issuer` 가 무의미한 답을 낸다(「수산금융채권일반」이 특은채로 잡힌다 —
  「산금」이 「수**산금**융」 안에 있어서다). 그 무의미한 답과 표제어의 계열을 비교하니
  옳은 것을 막았다: 공급망안정화 -> 한국수출입은행, 예보기금 -> 예금보험공사,
  경북지역 -> 경상북도. **가드는 판정할 자격이 있는 것으로만 짜야 한다.**

가드 4는 «확인» 이 아니라 «거부권» 이다 — 칸에서 만난 적이 없으면(n=0) 통과시킨다.
그러니 이 층은 master·mp-test 보다 **약하다**. 층 순서에서 그렇게 매긴다.

산출: kbond_issuer_near.json  {줄임말: {"canon":…, "how":…, "n":…, "med_bp":…}}
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

import kbond_issuer as K
import kbond_issuer_derive as DV

HERE = Path(__file__).parent
OUT = HERE / "kbond_issuer_near.json"

# 데스크가 쓰는 영문 약칭 <-> 한글 음차. 손으로 적은 것만 — 규칙으로 만들지 않는다.
TRANSLIT = [
    ("SK", "에스케이"), ("LG", "엘지"), ("HD", "에이치디"), ("LS", "엘에스"),
    ("KT", "케이티"), ("KB", "케이비"), ("GS", "지에스"), ("CJ", "씨제이"),
    ("BNK", "비엔케이"), ("DGB", "디지비"), ("JB", "제이비"), ("NH", "엔에이치"),
    ("IBK", "아이비케이"), ("HL", "에이치엘"), ("SC", "에스씨"), ("DL", "디엘"),
    ("OCI", "오씨아이"), ("HDC", "에이치디씨"), ("KCC", "케이씨씨"), ("IM", "아이엠"),
    ("MG", "엠지"), ("SGI", "에스지아이"), ("BGF", "비지에프"), ("AJ", "에이제이"),
]
MIN_LEN = 4           # 이보다 짧은 이름은 접두가 너무 흔해 못 쓴다
MAX_GAP = 6           # 길이 차이 상한
BP_VETO = 2.0         # 민평 검정이 «반대» 로 보는 문턱
N_VETO = 5            # 거부권을 행사하려면 칸이 이만큼은 있어야 한다


def translits(w):
    """음차 변형 — 영문 약칭은 **대소문자를 가리지 않는다**(문면에 'hd현대…' 가 있다)."""
    out = {w}
    for a, b in TRANSLIT:
        if w.upper().startswith(a):
            out.add(b + w[len(a):])
        if w.startswith(b):
            out.add(a + w[len(b):])
            out.add(a.lower() + w[len(b):])
    return out


def _mp_cells(cache=DV.CACHE):
    """(날짜·회차·만기) 칸마다 {머리말: 민평중앙값} — 거부권 판정에 쓴다."""
    df = pd.read_parquet(cache)
    df = df[df.mp.notna() & df.mat.notna()].copy()
    hs = df["raw"].map(DV.split)
    df["head"] = [h for h, _ in hs]
    df["ser"] = [s for _, s in hs]
    df = df[df.ser.notna()]
    g = df.groupby(["d", "ser", "mat", "head"])["mp"].median().reset_index()
    return [dict(zip(sub["head"], sub["mp"]))
            for _, sub in g.groupby(["d", "ser", "mat"]) if len(sub) > 1]


def build():
    # ⚠ 앵커에서 **이 층 자신의 산출은 뺀다**. 안 그러면 이번 유도가 지난 유도를
    #   근거로 삼아 되먹임이 생기고, 다시 돌릴 때마다 답이 달라진다(derive 와 같은 규율).
    heads = {h for h in K.RESOLVE if K.SOURCE.get(h) != "near"}
    cache = pd.read_parquet(DV.CACHE)
    raw = defaultdict(int)
    for r, n in cache["raw"].value_counts().items():
        c, how = K.canon_issuer(r)
        if how == "raw":
            raw[c] += n

    cells = _mp_cells()
    out, rejected = {}, []
    for name, n_rows in sorted(raw.items(), key=lambda kv: -kv[1]):
        nm = K._norm(name)
        if len(nm) < MIN_LEN:
            continue
        cand = set()
        how = None
        for v in translits(nm):
            if v in heads and v != nm:
                cand.add(K.RESOLVE[v]); how = "음차"
        longer = False
        if not cand:
            for v in translits(nm):
                short = {K.RESOLVE[h] for h in heads
                         if len(h) >= MIN_LEN and h != v and h.startswith(v)
                         and len(h) - len(v) <= MAX_GAP}
                if short:
                    cand |= short
                    how = "접미(문면이 짧다)"
            if not cand:
                for v in translits(nm):
                    lng = {K.RESOLVE[h] for h in heads
                           if len(h) >= MIN_LEN and h != v and v.startswith(h)
                           and len(v) - len(h) <= MAX_GAP}
                    if lng:
                        cand |= lng
                        how, longer = "접미(문면이 길다)", True
        cand.discard(name)
        if len(cand) != 1:
            if cand:
                rejected.append((n_rows, name, f"후보 {len(cand)}개", sorted(cand)[:3]))
            continue
        tgt = cand.pop()
        # 거부권 — 같은 칸에서 만난 적이 있는데 민평이 어긋나면 버린다
        d = [abs(c[name] - c[tgt]) * 100 for c in cells if name in c and tgt in c]
        med = float(pd.Series(d).median()) if d else None
        if d and len(d) >= N_VETO and med > BP_VETO:
            rejected.append((n_rows, name, f"민평이 어긋난다 {med:.1f}bp (n={len(d)})", [tgt]))
            continue
        # ★방향 B(문면이 더 길다)는 검정이 «확인» 해 줄 때만 받는다 — 위 주석 참조.
        if longer and not (d and med is not None and med <= 1.0):
            rejected.append((n_rows, name,
                             f"문면이 더 긴데 검정이 확인 안 함 (n={len(d)})", [tgt]))
            continue
        out[name] = {"canon": tgt, "how": how, "rows": int(n_rows),
                     "n": len(d), "med_bp": None if med is None else round(med, 2)}
    return out, rejected


if __name__ == "__main__":
    # ⚠ 굽기 전에 **자기 산출을 치운다.** 앵커(heads)만 거르면 모자란다 —
    #   «무엇이 아직 raw 인가» 를 정할 때 지난 산출이 이미 반영돼 있어서, 두 번째
    #   실행이 «남은 게 3종» 이라고 답한다(실측). 사전을 지우고 다시 읽어야 한다.
    import importlib
    if OUT.exists():
        OUT.unlink()
    importlib.reload(K)
    importlib.reload(DV)
    got, rej = build()
    OUT.write_text(json.dumps(got, ensure_ascii=False, indent=1), encoding="utf-8")
    rows = sum(v["rows"] for v in got.values())
    print(f"근접 부착 {len(got):,}종 · {rows:,}행  -> {OUT}")
    by = defaultdict(int)
    for v in got.values():
        by[v["how"]] += v["rows"]
    for k, v in by.items():
        print(f"    {k}: {v:,}행")
    print("\n== 붙은 것 상위 25 ==")
    for k, v in sorted(got.items(), key=lambda kv: -kv[1]["rows"])[:25]:
        chk = "검정 n=0" if v["n"] == 0 else f"검정 n={v['n']} {v['med_bp']}bp"
        print(f"  {v['rows']:7,}  {k:24s} -> {v['canon']:24s} [{v['how']} · {chk}]")
    print(f"\n== 가드가 막은 것 상위 15 (총 {len(rej):,}종) ==")
    for n, name, why, extra in sorted(rej, reverse=True)[:15]:
        print(f"  {n:7,}  {name:24s} {why}  {extra}")
