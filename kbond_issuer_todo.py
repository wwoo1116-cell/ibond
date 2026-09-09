# -*- coding: utf-8 -*-
"""판정 대기열 — 아직 못 접은 이름을 «값 순서로» 뽑는다 [OWNER 2026-09-09 「다 해라」].

## 왜 필요한가

자동 층 넷(master · near · mp-test · owner)을 다 걸고도 1.6% 가 남는다. 남은 것의
꼬리가 길어서(4,000종 넘음) 규칙으로는 끝이 안 난다. 그리고 그중 상당수는 «자료에
없는 발행체» 라 자동으로는 영영 못 붙인다 — 사람이 한 줄 적어 주면 끝나는 것들이다.

그래서 자동화 대신 **줄어드는 구조**를 둔다. 매번 상위 N 을 뽑아 판정하고, 판정한
것은 `kbond_issuer.OWNER` 에 적는다. 회차마다 꼬리가 짧아진다.

## 무엇을 같이 보여 주나

판정에 필요한 것만 붙인다 — 그 이름이 몇 행인지, 계열이 무엇으로 잡히는지,
문면 표본 둘, 그리고 **사전에 비슷한 이름이 있는지**(있으면 그게 답일 때가 많다).

    python kbond_issuer_todo.py            # 상위 30
    python kbond_issuer_todo.py 60         # 상위 60
    python kbond_issuer_todo.py --md       # 마크다운 표로(문서에 붙이기)
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

import kbond_issuer as K

HERE = Path(__file__).parent
LEDGER = Path(r"C:\Users\infomax\Projects\data\kbond\kbond_structured_data.parquet")


def similar(name, limit=3):
    """사전에 있는 비슷한 이름 — 접두를 공유하는 표제어. 판정을 거들 뿐 답이 아니다."""
    nm = K._norm(name)
    if len(nm) < 3:
        return []
    out = []
    for h in K.RESOLVE:
        if h == nm or len(h) < 3:
            continue
        if h.startswith(nm[:3]) or nm.startswith(h[:3]):
            tgt = K.RESOLVE[h]
            if tgt not in out and tgt != name:
                out.append(tgt)
        if len(out) >= limit:
            break
    return out


def collect():
    from kbond_live import classify_issuer
    f = pq.ParquetFile(LEDGER)
    rows = collections.Counter()
    ex = collections.defaultdict(list)
    for i in range(f.metadata.num_row_groups):
        t = f.read_row_group(i, columns=["Sector", "IssuerCanon", "IssuerSource",
                                         "Message"]).to_pandas()
        t = t[(t["Sector"].astype("string") == "크레딧/기타")
              & (t["IssuerSource"].astype("string") == "raw")]
        for ic, msg in zip(t["IssuerCanon"], t["Message"]):
            if ic is None or str(ic) == "nan":
                continue
            rows[str(ic)] += 1
            if len(ex[str(ic)]) < 2:
                ex[str(ic)].append(str(msg)[:88])
    return rows, ex, classify_issuer


if __name__ == "__main__":
    n_top = 30
    as_md = "--md" in sys.argv
    for a in sys.argv[1:]:
        if a.isdigit():
            n_top = int(a)
    rows, ex, classify = collect()
    tot = sum(rows.values())
    print(f"# 판정 대기열 — 안 접힌 이름 {len(rows):,}종 · {tot:,}행\n")
    if as_md:
        print("| 행 | 이름 | 계열 | 사전의 비슷한 이름 | 문면 |")
        print("|---:|---|---|---|---|")
    cum = 0
    for name, n in rows.most_common(n_top):
        cum += n
        sim = ", ".join(similar(name)) or "-"
        if as_md:
            print(f"| {n:,} | `{name}` | {classify(name)} | {sim} | "
                  f"`{ex[name][0][:60] if ex[name] else ''}` |")
        else:
            print(f"{n:7,}  {name:26s} [{classify(name)}]  ~ {sim}")
            for x in ex[name][:1]:
                print(f"          | {x}")
    print(f"\n상위 {n_top}종이 {cum:,}행 ({cum/tot*100:.1f}%). "
          f"판정한 것은 `kbond_issuer.OWNER` 에 적는다.")
