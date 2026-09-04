# -*- coding: utf-8 -*-
"""오너에게 보낼 «모르는 낱말» 목록을 만든다. [OWNER 지시 2026-09-02]

> 「은어 어떤 의미인지 내가 적어줄테니까 은어 나한테 표기로 보내줘」

## 어떻게 고르나

사전을 손으로 짜면 내가 아는 것만 나온다. 그래서 반대로 간다 —
**전 메시지의 한글 토큰을 세고, 설명할 수 있는 것을 빼고 남은 것**을 낸다.

빼는 것 넷:
  1. 매매 동사와 그 활용 (`RE_SELL` / `RE_BUY`)
  2. 섹터 규칙에 이미 든 낱말 (`SECTOR_RULES` 의 한글 리터럴 전부)
  3. **파서가 실제로 종목명으로 인정한 문자열**(`BondName` 고유값)의 토큰 —
     발행체 이름이지 은어가 아니다. 손으로 나열하지 않고 산출물에서 가져온다.
  4. 메시지 부속어 (호가·관심·억·원·민평·끝전 …)

남은 것을 빈도순으로 낸다. 각 낱말마다 실물 예문 셋과, 지금 그 행이 어떤
섹터·유형으로 처리되고 있는지를 붙인다. **처리가 되고 있어도 낱말 뜻을 모르면
목록에 남긴다** — 뜻을 모른 채 맞게 처리되고 있는 것과 틀리게 처리되고 있는 것을
오너가 갈라 주셔야 하기 때문이다.
"""
from __future__ import annotations

import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent))
from parse_kbond_logs import (RE_SELL, RE_BUY, SECTOR_RULES,        # noqa: E402
                              NAME_STOPWORDS, split_broker)

BASE = Path(r"C:\Users\infomax\Projects\data\kbond")
SRC = BASE / "kbond_structured_data.parquet"
OUT_XLSX = BASE / "kbond_은어_목록.xlsx"
OUT_MD = Path(__file__).parent / "SLANG_INVENTORY.md"

TOKEN = re.compile(r'[가-힣]{2,6}')
TOP_N = 200
MIN_COUNT = 300

# 메시지 부속어 — 은어가 아니라 문장을 이루는 말. 실물을 보고 골랐다.
FURNITURE = {
    "호가", "관심", "가능", "있나", "있나요", "있으", "있으신", "있으실", "있습",
    "찾습", "찾아", "부탁", "감사", "연락", "문의", "확인", "가격", "금리", "수익",
    "수익률", "잔존", "만기", "발행", "이자", "쿠폰", "표면", "액면", "단가", "평가",
    "민평", "민단", "끝전", "끝전은", "교체", "스위치", "역전", "동금리", "세트",
    "자투리", "짜투리", "물량", "수량", "전량", "일부", "잔량", "잔여", "체결",
    "거래", "결제", "당일", "익일", "내일", "오늘", "어제", "이번", "다음", "지난",
    "그리고", "또는", "이나", "이랑", "하고", "부터", "까지", "정도", "이상", "이하",
    "이내", "미만", "초과", "각각", "모두", "전부", "따로", "같이", "함께", "바로",
    "혹시", "아마", "아직", "이미", "다시", "계속", "우선", "먼저", "나중", "지금",
    "됩니", "합니", "입니", "습니", "니다", "세요", "해요", "네요", "구요", "군요",
    "죄송", "실례", "안녕", "수고", "고생", "빠른", "좋은", "적당", "충분",
    # 의문·어미 조각 — 1차 결과에 «실까요»·«신가요» 가 상위로 올라왔다.
    "실까요", "있으실까요", "신가요", "있으신가요", "으실까요", "으신가요",
    "실가요", "있으실가요", "매수호가", "매도호가", "호가있", "있으세요",
    "하실까요", "가능하", "possible",
}


def known_tokens(df_names: set[str]) -> set[str]:
    """설명 가능한 낱말을 모은다."""
    k = set(FURNITURE) | set(NAME_STOPWORDS)
    # 1) 동사
    for rx in (RE_SELL, RE_BUY):
        k |= set(re.findall(r'[가-힣]+', rx.pattern))
    # 2) 섹터 규칙의 한글 리터럴
    for _, rx in SECTOR_RULES:
        k |= set(re.findall(r'[가-힣]{2,}', rx.pattern))
    # 3) 파서가 인정한 종목명에서 나온 토큰 (발행체 이름)
    for nm in df_names:
        k |= set(TOKEN.findall(str(nm)))
    # 4) 브로커·데스크 이름. 서명을 떼도 본문에 남는 것이 있다.
    #    ★1차 실행이 이걸 안 해서 상위 20개가 전부 데스크명이었다
    #    («신한»·«채권투자팀»·«흥국증권»…). 목록이 통째로 쓸모없었다.
    for b in globals().get("_BROKERS", ()):
        k |= set(TOKEN.findall(str(b)))
    for b in globals().get("_SENDERS", ()):
        k |= set(TOKEN.findall(str(b)))
    # 5) 이미 해독해 파이프라인이 쓰고 있는 은어 — 뜻을 알므로 물을 것이 없다
    k |= {"오버", "언더", "통당", "통딱", "구통", "구구통", "삼통", "삼딱",
          "구삼통", "구구삼통", "통방", "국당", "국전", "국전전", "국전당", "국딱",
          "국주", "당팔", "당사", "선팔", "선사", "선네고", "동금리", "민스플",
          "짜툴", "자툴", "짜투리", "세트팔", "세트사", "셋팔", "셋사"}
    return k


def main() -> int:
    t0 = time.time()
    src = pq.ParquetFile(SRC)
    cols = ["Message", "BondName", "Sector", "MsgType", "Room", "Sender", "Broker"]

    cnt = Counter()
    senders = defaultdict(set)
    names: set[str] = set()
    brokers: set[str] = set()
    _senders: set[str] = set()
    print(f"[1/3] 토큰 세기 — 행그룹 {src.num_row_groups}개")
    msgs = []
    for rg in range(src.num_row_groups):
        d = src.read_row_group(rg, columns=cols).to_pandas()
        names |= set(d["BondName"].dropna().unique())
        # ★첫 판이 발신자 서명에 완전히 오염됐다 — 상위 20개가 전부 데스크 이름
        #   («신한»·«채권투자팀»·«흥국증권»…). 서명은 매 줄 끝에 붙으므로
        #   빈도 상위를 통째로 먹는다. 파서의 `split_broker` 로 떼고 본문만 센다.
        core = [split_broker(str(x))[1] for x in d["Message"]]
        brokers |= {str(x) for x in d["Broker"].dropna().unique()}
        _senders |= {str(x) for x in d["Sender"].dropna().unique()}
        for s, sender in zip(core, d["Sender"].astype(str)):
            for t in set(TOKEN.findall(s)):
                cnt[t] += 1
                if len(senders[t]) < 40:
                    senders[t].add(sender)
        dd = d[["Sector", "MsgType"]].copy()
        dd["Message"] = core                 # 예문도 본문만 보여 준다
        msgs.append(dd)
        print(f"      {rg + 1}/{src.num_row_groups}  고유 토큰 {len(cnt):,}", flush=True)
    msgs = pd.concat(msgs, ignore_index=True)
    print(f"      종목명 {len(names):,}종 · 브로커 {len(brokers):,}개")
    globals()["_BROKERS"] = brokers
    globals()["_SENDERS"] = _senders

    print("[2/3] 아는 낱말 빼기")
    known = known_tokens(names)
    left = [(t, n) for t, n in cnt.most_common() if t not in known and n >= MIN_COUNT]
    print(f"      전체 {len(cnt):,} -> 아는 것 제외 {len(left):,} "
          f"(빈도 {MIN_COUNT}회 이상)")

    print("[3/3] 예문·처리 상태 붙이기")
    rows = []
    M = msgs["Message"].astype(str)
    for t, n in left[:TOP_N]:
        # ★순위는 토큰으로 매기면서 행수·예문을 부분문자열로 세면 어긋난다.
        #   «도공» 에 「철도공단」 예문이 붙어 오너가 헷갈린다. 같은 경계를 쓴다.
        hit = M.str.contains(r"(?<![가-힣])" + re.escape(t) + r"(?![가-힣])",
                             regex=True, na=False)
        g = msgs[hit]
        ex = [x for x in g["Message"].astype(str).drop_duplicates().head(3)]
        sec = g["Sector"].fillna("(없음)").value_counts()
        typ = g["MsgType"].fillna("(없음)").value_counts()
        rows.append({
            "은어": t,
            "행수": int(hit.sum()),
            "발신자수": len(senders[t]),
            "지금 섹터": f"{sec.index[0]} {100 * sec.iloc[0] / len(g):.0f}%" if len(sec) else "",
            "지금 유형": f"{typ.index[0]} {100 * typ.iloc[0] / len(g):.0f}%" if len(typ) else "",
            "뜻 (여기에 적어주세요)": "",
            "예문1": ex[0][:120] if len(ex) > 0 else "",
            "예문2": ex[1][:120] if len(ex) > 1 else "",
            "예문3": ex[2][:120] if len(ex) > 2 else "",
        })
        if len(rows) % 25 == 0:
            print(f"      {len(rows)}/{min(TOP_N, len(left))}", flush=True)

    out = pd.DataFrame(rows).sort_values("행수", ascending=False)
    write(out, time.time() - t0)
    return 0


def write(out: pd.DataFrame, secs: float):
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    tmp = OUT_XLSX.with_suffix(".xlsx.tmp")
    with pd.ExcelWriter(tmp, engine="openpyxl") as xw:
        out.to_excel(xw, index=False, sheet_name="은어")
        ws = xw.sheets["은어"]
        widths = {"은어": 12, "행수": 10, "발신자수": 10, "지금 섹터": 16,
                  "지금 유형": 14, "뜻 (여기에 적어주세요)": 34,
                  "예문1": 60, "예문2": 60, "예문3": 60}
        for i, c in enumerate(out.columns, start=1):
            ws.column_dimensions[get_column_letter(i)].width = widths.get(c, 14)
        head = PatternFill("solid", fgColor="1F3B4D")
        for c in range(1, len(out.columns) + 1):
            cell = ws.cell(row=1, column=c)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = head
            cell.alignment = Alignment(vertical="center")
        # 적는 칸을 눈에 띄게
        ans = list(out.columns).index("뜻 (여기에 적어주세요)") + 1
        fill = PatternFill("solid", fgColor="FFF6D8")
        for r in range(2, len(out) + 2):
            ws.cell(row=r, column=ans).fill = fill
        ws.freeze_panes = "B2"
        ws.auto_filter.ref = ws.dimensions
    import os
    os.replace(tmp, OUT_XLSX)

    L = ["# 모르는 낱말 목록 (오너 기입용)", "",
         f"실행 2026-09-02 · 빈도 {MIN_COUNT}회 이상 · 상위 {len(out)}개 · {secs:,.0f}초", "",
         "동사·섹터어·발행체명·문장 부속어를 뺀 나머지다. **처리가 되고 있어도**",
         "낱말 뜻을 모르면 남겼다 — 맞게 처리되는 것과 틀리게 처리되는 것을",
         "가려 주셔야 하기 때문이다.", "",
         "| 은어 | 행수 | 발신자 | 지금 섹터 | 지금 유형 | 예문 |",
         "|---|---|---|---|---|---|"]
    for r in out.head(60).itertuples():
        ex = getattr(r, "예문1", "").replace("|", "/")[:70]
        L.append(f"| `{r.은어}` | {r.행수:,} | {r.발신자수} | {r._5} | {r._6} | `{ex}` |")
    OUT_MD.write_text("\n".join(L), encoding="utf-8")
    print(f"\n  -> {OUT_XLSX}  ({len(out)}개)")
    print(f"  -> {OUT_MD}")


if __name__ == "__main__":
    sys.exit(main())
