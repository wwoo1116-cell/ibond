# -*- coding: utf-8 -*-
"""뜻 관문 — 원장이 «뜻» 을 제대로 담고 있는지 채점한다. 재파싱 뒤마다 돌린다.

[OWNER 2026-09-07] 「규칙을 더 조밀하게 만드는 게 나을까? 오류가 없었으면 하거든」
에 대한 답이 이 파일이다. 뜻 규칙(AtMP 같은)은 라벨이 없어 «맞았는지» 를 직접 못 잰다.
대신 **뜻이 참이면 따라 나와야 하는 결과**를 재고, 그 숫자를 기준선에 박는다.
규칙을 고칠 때마다 이 숫자가 유지되는지 보면 «조밀하게 만든 것» 이 옳았는지 알 수 있다.

  [J] 뜻 관문   «민평에 팔자» 가 참이면 그 뒤 체결이 민평에서 찍혀야 한다.
                기준선 2026-09-07(재파싱 뒤): 91.7% n=1,442 (기저 39.8%) · 배관검증 98.7%
  [K] 놓친 레벨  문면에 값이 있는데 안 읽힌 행. 0 이 목표가 아니라 «튀지 않는 것» 이 목표다.
                기준선 2026-09-07(재파싱 뒤): 무단위 민±N 4,710행
  [L] 커버리지   계열별 레벨 채움 비율. 떨어지면 어딘가 규칙이 좁아진 것이다.

실행:  python gate_meaning.py            (실패하면 종료코드 1)
"""
from __future__ import annotations

import re
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

BASE = r"C:\Users\infomax\Projects\data\kbond"
WIN = 7200.0
# 기준선 — 값이 아니라 «떨어지면 안 되는 바닥» 이다. 고칠 때마다 근거와 함께 갱신할 것.
# 2026-09-07 재파싱 «뒤» 실측으로 갱신. 앞 숫자는 재파싱 전(87.3% · 4,356)이었다.
BASE_J, BASE_J_MIN = 91.7, 80.0
BASE_K, BASE_K_MAX = 4710, 6000
RE_NOUNIT = re.compile(r'민\s*평?\s*[+\-]\s*\d{1,3}(?:\.\d{1,2})?(?!\s*(?:bp|비피|빕|삡|원|\d))')


def secs(s):
    return s.astype("datetime64[ns]").astype("int64").to_numpy() / 1e9


def main() -> int:
    fails = []
    QC = ['Date', 'Timestamp', 'Sector', 'Position', 'MsgType', 'SpreadValue',
          'AbsYield', 'QuoteRaw', 'QuoteVsMP_bp', 'QuoteYield', 'MPYield',
          'Maturity', 'Broker', 'IsInquiry', 'Message', 'AtMP']
    q = pq.read_table(BASE + r"\kbond_structured_data.parquet", columns=QC).to_pandas()
    f = pd.read_parquet(BASE + r"\kbond_fills.parquet",
                        columns=['Date', 'Timestamp', 'Sector', 'QuoteVsMP_bp',
                                 'MPYield', 'Maturity', 'Broker', 'RepostSeq'])
    print(f"원장 {len(q):,}행 · 체결 {len(f):,}행")

    # ── [J] 뜻 관문 ─────────────────────────────────────────────────────
    g = q[(q.Sector == '크레딧/기타') & (q.MsgType == 'QUOTE') & (q.Position == 'SELL')
          & (~q.IsInquiry.fillna(False)) & q.MPYield.notna() & q.Maturity.notna()].copy()
    ff = f[(f.Sector == '크레딧/기타') & (f.RepostSeq == 0) & f.QuoteVsMP_bp.notna()
           & f.MPYield.notna() & f.Maturity.notna()].copy()
    g['ts'], ff['ts'] = secs(g.Timestamp), secs(ff.Timestamp)
    g['noL'] = g.SpreadValue.isna() & g.AbsYield.isna() & g.QuoteRaw.isna()
    g['mp3'], ff['mp3'] = g.MPYield.round(3), ff.MPYield.round(3)
    gg = {k: v.sort_values('ts')
          for k, v in g.groupby(['Date', 'Broker', 'Maturity', 'mp3'], sort=False)}
    A, C, Cd = [], [], []
    for r in ff.itertuples():
        s = gg.get((r.Date, r.Broker, r.Maturity, r.mp3))
        if s is None:
            continue
        p = s[(s.ts <= r.ts) & (s.ts >= r.ts - WIN)]
        if p.empty:
            continue
        last = p.iloc[-1]
        v = float(r.QuoteVsMP_bp)
        if last.noL:
            A.append(v)
        elif not pd.isna(last.QuoteVsMP_bp):
            C.append(v); Cd.append(v - float(last.QuoteVsMP_bp))
    A, Cd = pd.Series(A, dtype=float), pd.Series(Cd, dtype=float)
    base = (ff.QuoteVsMP_bp.abs() <= 1).mean() * 100
    hit = (A.abs() <= 1).mean() * 100 if len(A) else float('nan')
    plumb = (Cd.abs() <= 1).mean() * 100 if len(Cd) else float('nan')
    print(f"\n[J] 뜻 관문 — «민평에 팔자» 뒤 체결이 민평 ±1bp 에서 찍힌 비율")
    print(f"    처치 {hit:.1f}% (n={len(A):,}) · 기저 {base:.1f}% · 기준선 {BASE_J}%")
    print(f"    배관검증(값 있는 호가는 그 값에서) {plumb:.1f}% (n={len(Cd):,})")
    if len(A) < 200:
        fails.append(f"J0 표본이 너무 적다 n={len(A)}")
    elif hit < BASE_J_MIN:
        fails.append(f"J1 뜻 관문 {hit:.1f}% < {BASE_J_MIN}% — «민평에» 규칙을 의심할 것")
    if plumb < 90:
        fails.append(f"J2 배관검증 {plumb:.1f}% < 90% — 연결(딜러·종목·민평)이 깨졌다")

    # ── [K] 놓친 레벨 ───────────────────────────────────────────────────
    qa = q[q.MsgType.isin(['QUOTE', 'AXE']) & q.Position.isin(['BUY', 'SELL'])
           & (~q.IsInquiry.fillna(False))]
    noL = qa.SpreadValue.isna() & qa.AbsYield.isna() & qa.QuoteRaw.isna()
    core = qa.Message.fillna('').astype(str)
    k_n = int(core[noL].str.contains(RE_NOUNIT, regex=True, na=False).sum())
    print(f"\n[K] 놓친 레벨 — 무단위 «민±N» {k_n:,}행 (기준선 {BASE_K:,})")
    if k_n > BASE_K_MAX:
        fails.append(f"K1 무단위 민±N 이 {k_n:,} 로 늘었다 (> {BASE_K_MAX:,}) — 새 문형을 볼 것")

    # ── [L] 계열별 레벨 커버리지 ────────────────────────────────────────
    print("\n[L] 계열별 레벨 커버리지 (원장)")
    lv = qa.QuoteYield.notna() | qa.QuoteVsMP_bp.notna()
    t = pd.DataFrame({'n': qa.groupby('Sector').size(),
                      'lv': lv.groupby(qa.Sector).sum()}).dropna()
    t = t[t.n >= 5000].sort_values('n', ascending=False)
    for s, r in t.iterrows():
        print(f"    {s:14s} {int(r.n):9,} · 레벨 {r.lv / r.n * 100:5.1f}%")
    print(f"    {'전체':14s} {len(qa):9,} · 레벨 {lv.mean() * 100:5.1f}%")

    print("\n" + "=" * 56)
    if fails:
        print(f"실패 {len(fails)}건")
        for x in fails:
            print("  -", x)
        return 1
    print("전건 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
