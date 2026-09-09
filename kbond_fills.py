# -*- coding: utf-8 -*-
"""체결 기록 테이블 (kbond_fills). [OWNER 승인 2026-09-01]

## 왜 별도 표인가

`MsgType=='CONFIRM'` 은 두 종류가 섞여 있다.

    ㅎㅈ                                          <- 짧은 확정 응답. 값이 없다.
    26.1.24 하나은행 (민 2.820 끝.25) -1.25원 2.835% 400억 체결 후 잔존 100억
                                                  <- 종목·방향·레벨·수량이 온전한 사후 보고

전수조사(2026-09-01)에서 뒤쪽이 **42,146행**으로 세어졌다. 이건 호가가 아니라
**실제로 붙은 거래의 기록**이라 호가 표와 섞어 두면 둘 다 못 쓴다. 호가 분포를
재는 분석은 체결을 빼야 하고, 체결 분석은 호가를 빼야 한다.

## 무엇을 담는가

**값을 하나라도 가진** 행 중, `MsgType=='CONFIRM'` 이거나 본문에 '체결/거래' 가 있는 것.
값이 없는 순수 'ㅎㅈ' 은 여기 오지 않는다(직전 호가와 링크해야 레벨이 생긴다 — 미구현).

CONFIRM 만으로 좁히지 않는 이유가 있다. «26.3.31 IBK캐피탈 +1원 2.780 **체결후
추가팔자**» 같은 문형은 **한 메시지가 두 역할**을 한다 — 체결 사실을 보고하면서
동시에 새 호가를 낸다. `MsgType` 은 주된 행위(호가)를 따라 QUOTE 로 두되,
체결 사실은 여기서 잃지 않는다. 실측 23,150행.

`FillKind`
  - `reported`  : 체결가·수량이 문면에 적힌 사후 보고 (레벨 신뢰도 높음)
  - `ack_with_quote` : 확정 응답에 호가가 같이 붙은 것
  - `reported_then_quote` : 체결 보고 + 새 호가 복합문 (MsgType 은 QUOTE)

`Residual` : '체결 후 잔존 100억' 처럼 남은 물량이 적힌 경우 그 수량.

## 한계 (읽는 사람이 알아야 할 것)

- **이건 체결 «보고» 이지 체결 «확인» 이 아니다.** 같은 거래가 양쪽에서 두 번
  보고되면 두 행이 된다. **2026-09-07 부터 `DupSeq` 로 표시한다**(지우지는 않는다) —
  같은 (일·종목·레벨·수량) 을 다른 브로커가 5초 안에 각각 보고한 것. 첫 보고가 0.
  창을 5초로 고른 근거는 실측이다: 이웃 쌍의 «같은 수량» 비율이 기저 39.7% 인데
  0~5초 구간만 54.1% 로 솟고 5~20초는 40.2% 로 이미 기저다.
  ⚠수량은 «명시된 것» 으로 재야 그 솟음이 보인다(AmountEff 는 미표기를 100억으로 채운다).
- 순수 'ㅎㅈ' 104,931행이 빠져 있으므로 **체결 건수의 하한**이다.
- `QuoteYield` 는 호가 표와 같은 파이프라인(enrich)이 만든 값이라 그 한계를
  그대로 물려받는다.
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

BASE = Path(r"C:\Users\infomax\Projects\data\kbond")
SRC = BASE / "kbond_structured_data.parquet"
OUT = BASE / "kbond_fills.parquet"
# T16: 최종 경로에 직접 쓰면 도중에 죽었을 때 새 것도 없고 직전 것도 없다.
TMP = BASE / "kbond_fills.parquet.tmp"

COLS = ["Date", "Time", "Timestamp", "Room", "Sender", "Message",
        "Position", "Sector", "BondCode", "SeriesNo", "BondName", "Maturity",
        "MPYield", "MPYieldDB", "QuoteYield", "QuoteMethod", "QuoteVsMP_bp",
        "SpreadValue", "SpreadUnit", "SpreadSource", "AbsYield", "QuoteRaw",
        "Amount", "AmountEff", "AmountSource", "Broker", "MsgType", "SourceFile"]
VALUE_COLS = ["MPYield", "AbsYield", "QuoteRaw", "SpreadValue", "QuoteYield"]

# '체결 후 잔존 100억' / '거래 후 잔량 50억'
DUP_WIN = 5.0   # 양쪽 보고 중복으로 볼 시차 상한(초). 실측으로 고른 값 — 위 주석 참조

RE_RESIDUAL = re.compile(r'(?:잔존|잔량|잔여)\s*(\d{1,4}(?:\.\d+)?)\s*억')
RE_REPORTED = re.compile(r'체결|거래')
# 체결어와 6자 이내 인접한 억 = 체결 수량(감사: 8,242행이 이 조건 충족).
RE_FILL_AMOUNT = re.compile(r'(\d{1,4}(?:\.\d+)?)\s*억[^\d]{0,6}(?:체결|거래)'
                            r'|(?:체결|거래)[^\d]{0,8}(\d{1,4}(?:\.\d+)?)\s*억')


def main() -> int:
    if not SRC.exists():
        sys.exit(f"[FATAL] 없음: {SRC}")
    t0 = time.time()
    src = pq.ParquetFile(SRC)
    have = set(src.schema_arrow.names)
    cols = [c for c in COLS if c in have]

    writer, schema = None, None
    n_seen = n_fill = 0
    kinds: dict[str, int] = {}
    try:
        for rg in range(src.num_row_groups):
            df = src.read_row_group(rg, columns=cols).to_pandas()
            # CONFIRM 뿐 아니라 «거래 후 추가팔자» 처럼 MsgType 은 QUOTE 이면서
            # 체결 사실을 담은 행도 받는다(한 메시지가 두 역할을 한다).
            _m = df["Message"].astype(str)
            df = df[df["MsgType"].eq("CONFIRM")
                    | _m.str.contains(RE_REPORTED, regex=True, na=False)]
            n_seen += len(df)
            if not len(df):
                continue
            has_val = df[[c for c in VALUE_COLS if c in df.columns]].notna().any(axis=1)
            df = df[has_val].copy()
            if not len(df):
                continue
            msg = df["Message"].astype(str)
            df["FillKind"] = pd.Series(
                ["reported" if RE_REPORTED.search(m) else "ack_with_quote" for m in msg],
                index=df.index, dtype="object")
            # 체결 보고에 새 호가가 붙은 복합문(«거래 후 추가팔자»)은 따로 표시한다.
            df.loc[msg.str.contains(r"(?:체결|거래)\s*(?:후|뒤)", regex=True, na=False)
                   & df["MsgType"].ne("CONFIRM"), "FillKind"] = "reported_then_quote"
            df["Residual"] = pd.to_numeric(
                msg.str.extract(RE_RESIDUAL, expand=False), errors="coerce")
            # ★2026-09-01 감사: Amount 는 문장의 첫 '억' 을 집어 잔존물량·권종이
            # 섞인다. 체결어와 6자 이내 인접한 억만 체결 수량으로 본다.
            _fa = msg.str.extract(RE_FILL_AMOUNT)          # 그룹 2개(앞/뒤 어순)
            df["FillAmount"] = pd.to_numeric(
                _fa[0].fillna(_fa[1]), errors="coerce")
            # 같은 발신자의 재게시가 중복의 지배적 기전이다(감사: 그룹의 77%).
            # 건수를 세지 못하게 순번을 붙인다.
            df["RepostSeq"] = df.groupby(
                ["Date", "Room", "Sender", "Message"]).cumcount()
            for k, v in df["FillKind"].value_counts().items():
                kinds[k] = kinds.get(k, 0) + int(v)

            tbl = pa.Table.from_pandas(df, preserve_index=False)
            if writer is None:
                schema = tbl.schema
                writer = pq.ParquetWriter(TMP, schema, compression="zstd")
            writer.write_table(tbl.cast(schema))
            n_fill += len(df)
            print(f"  행그룹 {rg + 1}/{src.num_row_groups}  체결 누적 {n_fill:,}", flush=True)
    except BaseException:
        if writer is not None:
            writer.close()
            writer = None
        TMP.unlink(missing_ok=True)
        raise
    finally:
        if writer is not None:
            writer.close()
        src.close()

    os.replace(TMP, OUT)

    # ── 양쪽 보고 중복 표시 (DupSeq) [OWNER 2026-09-07] ─────────────────
    # RepostSeq 는 «같은 발신자의 재게시» 다. 그것과 별개로, 같은 거래를 «다른
    # 브로커» 가 각자 보고하면 두 행이 된다 — 이 표의 알려진 한계였다.
    #
    # ★자를 자리를 데이터에서 찾았다(2026-09-07). 같은 (일·종목·레벨·수량) 이웃 쌍의
    #   «같은 수량» 비율은 기저 39.7% 인데, 시차 0~5초 구간만 54.1% 로 솟는다
    #   (5~20초는 40.2% 로 이미 기저다). 그래서 창은 5초다.
    #   ⚠수량은 «명시된 것» 으로만 재야 한다 — AmountEff 는 미표기를 100억으로 채워
    #     «같은 수량» 이 부풀고, 그러면 짧은 구간의 솟음이 안 보인다(처음에 그렇게 놓쳤다).
    #
    # ★지우지 않는다. RepostSeq 선례대로 순번만 붙인다 — DupSeq==0 이 첫 보고다.
    #   실측 2,978건(재게시 제외 체결의 4.7%) · 국고 2,343 · 통안 541 · 크레딧 94.
    #   그중 13%는 «같은 하우스의 다른 전화선» 이다(서명 XXXX-XXXX).
    fdf = pd.read_parquet(OUT)
    fdf["DupSeq"] = 0
    _ts = fdf["Timestamp"].astype("datetime64[ns]").astype("int64").to_numpy() / 1e9
    _key = (fdf["BondCode"].fillna("") + "|" + fdf["BondName"].fillna("")
            + "|" + fdf["Maturity"].fillna("")
            + "|" + fdf["QuoteYield"].round(3).astype(str)
            + "|" + fdf["AmountEff"].fillna(-1).astype(str))
    _ord = np.argsort(_ts, kind="stable")
    _seq = np.zeros(len(fdf), dtype="int64")
    _last = {}                       # (Date, key) -> (시각, 브로커, 순번)
    _dates = fdf["Date"].to_numpy()
    _brk = fdf["Broker"].fillna("").to_numpy()
    _rep = fdf["RepostSeq"].to_numpy()
    _k = _key.to_numpy()
    for ix in _ord:
        if _rep[ix] > 0:
            continue                 # 재게시는 RepostSeq 가 이미 표시한다
        kk = (_dates[ix], _k[ix])
        prev = _last.get(kk)
        if prev is not None and _ts[ix] - prev[0] <= DUP_WIN and _brk[ix] != prev[1]:
            _seq[ix] = prev[2] + 1
        _last[kk] = (_ts[ix], _brk[ix], _seq[ix])
    fdf["DupSeq"] = _seq
    fdf.to_parquet(TMP, compression="zstd", index=False)
    os.replace(TMP, OUT)
    print(f"  양쪽 보고 중복 표시 DupSeq>0 {int((_seq > 0).sum()):,}건 "
          f"({100 * (_seq > 0).mean():.1f}%) — 지우지 않고 표시만")

    print("\n" + "=" * 66)
    print(f"  CONFIRM 전체        {n_seen:,}")
    print(f"  값을 가진 체결 기록   {n_fill:,}  ({100 * n_fill / max(n_seen, 1):.1f}%)")
    print(f"  값 없는 순수 확정     {n_seen - n_fill:,}  (직전 호가 링크 미구현 — 하한)")
    print("\n  FillKind")
    for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]):
        print(f"    {k:<16} {v:>9,}")
    if OUT.exists():
        print(f"\n  -> {OUT}  ({OUT.stat().st_size / 2 ** 20:,.1f} MB)  {time.time() - t0:,.0f}초")
    return 0


if __name__ == "__main__":
    sys.exit(main())
