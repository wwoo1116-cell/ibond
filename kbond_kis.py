# -*- coding: utf-8 -*-
"""KIS자산평가 예상종가 표 파서 (kbond_kis_curve). [OWNER 승인 2026-09-01]

## 무엇인가

KIS자산평가가 장 마감 무렵 메신저에 뿌리는 커브 스냅샷이다. 422행 · 335 영업일.

    : KIS 자산평가 예상 종가입니다.
    1년통 3.385 ( 2.0 )  1.5년통 3.490 ( 6.0 )  구통 3.487 ( 6.5 )
    통당  3.462 ( 6.5 )  삼통당  3.495 ( 6.8 )
    ===================== 14-2 3.450 ( -0.5 )  19-1 3.450 ( -0.5 ) …  (2Y)
                          … 23-8 3.475 ( 6.0 )  (2Y)   15-8 … 23-10 …  (3Y)

한 표에 **통안 은어별 금리**와 **국고 지표물 금리**가 같이 들어 있고, 국고는
만기 표지 `(2Y)`~`(30Y)` 로 묶여 있다. 괄호 안 숫자는 전일 대비 변화(bp).

## 왜 쓰는가

**은어→종목 배정의 독립 검증축**이다. 우리가 `구통`을 「2년물 직전 발행」으로
배정했는데, 그 배정이 맞다면 KIS 가 적은 `구통` 금리와 우리가 붙인 민평이
날마다 맞아야 한다. 파이프라인이 만든 파생열이 아니라 **외부 관측치**라
순환논증을 피한다.

덤으로 `1.5년통` 처럼 우리 사전에 없던 은어가 여기서 드러난다.

## 한계

- '예상' 종가다. 확정치가 아니다.
- 335일치라 전체 640 영업일의 52% 만 덮는다.
- 값 복원에 쓰려면 `QuoteMethod='kis_est'` 로 갈라 출처를 남길 것. 현재는
  **검증 전용**이고 본표에 흘려보내지 않는다.
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

import pandas as pd

BASE = Path(r"C:\Users\infomax\Projects\data\kbond")
SRC = BASE / "kbond_structured_data.parquet"
OUT = BASE / "kbond_kis_curve.parquet"

RE_HEAD = re.compile(r"KIS\s*자산평가|예상\s*종가")
# '<이름> <금리> ( <변화> )'  이름 = 통안 은어 또는 국고 지표코드.
# ⚠ 은어를 낱말 목록으로 못 박는다. '[가-힣]{2,5}통' 같은 얼개로 잡으면
#   '구통'(통 앞이 한 자)을 놓치고 '통당·삼통당'(당으로 끝난다)도 못 잡는다.
#   긴 낱말을 앞에 둘 것 — 구구삼통이 삼통보다, 구구통이 구통보다 먼저.
MSB_NAMES = (r"구구삼통|구삼통|구구통|구통당|삼통당|구통|삼통|통당|통딱|삼딱"
             r"|\d{1,2}(?:\.\d)?\s*년통|\d{1,3}\s*일통")
RE_ITEM = re.compile(rf"({MSB_NAMES}|\d{{2}}-\d{{1,2}})"
                     r"\s*[\t ]\s*(\d\.\d{2,4})\s*\(\s*(-?\d+(?:\.\d+)?)\s*\)")
RE_IS_MSB = re.compile(rf"^(?:{MSB_NAMES})$")
RE_TENOR = re.compile(r"\((\d{1,2})Y\)")


def parse_one(msg: str):
    """한 표에서 (이름, 금리, 변화bp, 만기표지) 행들을 뽑는다."""
    out = []
    pos = 0
    for m in RE_ITEM.finditer(msg):
        name, y, chg = m.group(1), float(m.group(2)), float(m.group(3))
        # 이 항목 뒤 가장 가까운 만기 표지를 찾는다(그룹 끝에 붙는다)
        nxt = RE_TENOR.search(msg, m.end())
        tenor = f"{nxt.group(1)}Y" if nxt else None
        kind = "MSB" if RE_IS_MSB.match(name) else "KTB"
        out.append((name, y, chg, tenor if kind == "KTB" else None, kind))
        pos = m.end()
    return out


def main() -> int:
    if not SRC.exists():
        sys.exit(f"[FATAL] 없음: {SRC}")
    t0 = time.time()
    df = pd.read_parquet(SRC, columns=["Date", "Time", "Room", "Sender", "Message"])
    hit = df["Message"].astype(str).str.contains(RE_HEAD, regex=True, na=False)
    df = df[hit].copy()
    print(f"  KIS 표 {len(df):,}행 · {df['Date'].nunique()}일")

    rows = []
    for r in df.itertuples(index=False):
        for name, y, chg, tenor, kind in parse_one(str(r.Message)):
            rows.append({"Date": r.Date, "Time": r.Time, "Room": r.Room,
                         "Sender": r.Sender, "Name": name, "Yield": y,
                         "ChgBp": chg, "Tenor": tenor, "Kind": kind})
    out = pd.DataFrame(rows)
    if not len(out):
        sys.exit("[FATAL] 파싱 0행")
    # 같은 날 여러 번 뿌리면 마지막 것만
    out = out.sort_values(["Date", "Time"]).drop_duplicates(
        ["Date", "Name"], keep="last").reset_index(drop=True)
    # T16: 최종 경로에 직접 쓰면 도중에 죽었을 때 직전 산출물까지 같이 잃는다.
    tmp = OUT.with_suffix(".parquet.tmp")
    try:
        out.to_parquet(tmp, index=False, compression="zstd")
        os.replace(tmp, OUT)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise

    print(f"\n  파싱 {len(out):,}행 (일자 {out['Date'].nunique()})")
    print(f"  종류: {out['Kind'].value_counts().to_dict()}")
    print("\n  통안 은어별 관측 일수")
    msb = out[out.Kind.eq("MSB")]
    for k, v in msb["Name"].value_counts().items():
        print(f"    {k:<10} {v:>5}일   금리 중앙 {msb[msb.Name.eq(k)]['Yield'].median():.3f}")
    print("\n  국고 만기표지별 종목수")
    ktb = out[out.Kind.eq("KTB")]
    print("   ", ktb.groupby("Tenor")["Name"].nunique().to_dict())
    print(f"\n  -> {OUT}  ({OUT.stat().st_size / 2**10:,.0f} KB)  {time.time() - t0:,.0f}초")
    return 0


if __name__ == "__main__":
    sys.exit(main())
