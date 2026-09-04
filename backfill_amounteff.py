# -*- coding: utf-8 -*-
"""본표에 AmountEff·AmountSource 를 소급한다. [OWNER 2026-09-03]

「AmountEff 만 소급, OddLot 은 그대로」 — 기존 OddLot 열은 손대지 않는다(연구 코드가
읽는 열이다). 다만 AmountEff 계산에는 넓힌 자툴류 규칙을 «본문에서» 직접 본다.
규칙은 parse_kbond_logs 의 대입부와 같아야 한다:

    stated  = Amount 가 있고 AmountImplied 아님
    implied = Amount 가 있고 AmountImplied
    oddlot  = 자투리·짜투리·자툴·짜툴·잔량 -> None
    bare    = 동사 뒤 단위 없는 맨숫자(10의 배수 10~1000, CD·CP 제외)
    default = 그 밖 -> 100억
    적용 대상 = QUOTE · AXE · «내용 있는» CONFIRM. 나머지는 None.

실행:  python backfill_amounteff.py            (원자 교체)
       python backfill_amounteff.py --dry      (쓰지 않고 분포만)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent))
from parse_kbond_logs import RE_ODDLOT, LOT_DEFAULT, bare_amount  # noqa: E402

SRC = Path(r"C:\Users\infomax\Projects\data\kbond\kbond_structured_data.parquet")
TMP = SRC.with_suffix(".parquet.tmp")
CHUNK = 300_000


def eff(df: pd.DataFrame):
    msg = df["Message"].astype(str)
    body = bool  # noqa
    has = (df["BondCode"].notna() | df["BondName"].notna() | df["Maturity"].notna()
           | df["QuoteRaw"].notna() | df["AbsYield"].notna())
    ok = df["MsgType"].isin(["QUOTE", "AXE"]) | (df["MsgType"].eq("CONFIRM") & has)

    src = pd.Series(pd.NA, index=df.index, dtype=object)
    val = pd.Series(np.nan, index=df.index, dtype="float64")

    amt = pd.to_numeric(df["Amount"], errors="coerce")
    imp = df["AmountImplied"].fillna(False).astype(bool)
    m_stated = ok & amt.notna()
    val[m_stated] = amt[m_stated]
    src[m_stated & imp] = "implied"
    src[m_stated & ~imp] = "stated"

    rest = ok & ~m_stated
    m_odd = rest & msg.str.contains(RE_ODDLOT, na=False)
    src[m_odd] = "oddlot"                      # 값은 NaN 그대로 (수량 미상)

    rest2 = rest & ~m_odd
    # ★규칙은 parse_kbond_logs.bare_amount 하나만 쓴다(예전엔 여기서 따로 구현해
    #   파서를 고쳐도 백필에 안 먹었다).
    idx = df.index[rest2]
    bv = pd.Series(
        [bare_amount(t, sc) for t, sc in zip(msg[idx], df["Sector"][idx])],
        index=idx, dtype="float64")
    m_bare = pd.Series(False, index=df.index)
    m_bare[idx] = bv.notna()
    val[m_bare] = bv[bv.notna()]
    src[m_bare] = "bare"

    m_def = rest2 & ~m_bare
    val[m_def] = LOT_DEFAULT
    src[m_def] = "default"
    return val, src


def main() -> int:
    dry = "--dry" in sys.argv
    t0 = time.time()
    f = pq.ParquetFile(SRC)
    base = f.schema_arrow
    add = [x for x in ("AmountEff", "AmountSource") if x not in base.names]
    schema = pa.schema(list(base) + [pa.field("AmountEff", pa.float64()),
                                     pa.field("AmountSource", pa.string())]
                       ) if add else base
    print(f"[1/2] {SRC.name} {f.metadata.num_rows:,}행 · {len(base.names)}열 "
          f"-> {len(schema.names)}열")
    writer = None if dry else pq.ParquetWriter(TMP, schema, compression="zstd")
    from collections import Counter
    tot = Counter()
    n = 0
    try:
        for batch in f.iter_batches(batch_size=CHUNK):
            df = batch.to_pandas()
            v, s = eff(df)
            df["AmountEff"] = v
            df["AmountSource"] = s.astype(object)
            tot.update(s.fillna("(없음)").tolist())
            n += len(df)
            if writer is not None:
                writer.write_table(
                    pa.Table.from_pandas(df[schema.names], preserve_index=False)
                    .cast(schema))
            print(f"      {n:,}행 ({time.time() - t0:.0f}초)", end="\r")
    finally:
        if writer is not None:
            writer.close()
        f.close()      # ★윈도우는 열린 핸들이 있으면 원자 교체가 막힌다
    print()
    print("[2/2] AmountSource 분포")
    for k, c in tot.most_common():
        print(f"      {k:10s} {c:>10,}  ({100 * c / n:.1f}%)")
    if dry:
        print("dry — 쓰지 않았다")
        return 0
    bak = SRC.with_suffix(".parquet.bak-v7")
    if not bak.exists():
        SRC.replace(bak)
    else:
        SRC.unlink()
    TMP.replace(SRC)
    print(f"교체 완료 ({time.time() - t0:.0f}초) · 이전 판 {bak.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
