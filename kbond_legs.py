# -*- coding: utf-8 -*-
"""한 메시지에 여러 종목이 든 발언을 종목 단위로 펼친다 (M1). [OWNER 승인 2026-09-01]

## 다리 경계 규칙

경계는 **종목 식별자가 아니라 매매 동사**로 정해진다.
식별자로 세면 안 되는 이유는 실측이다. QUOTE 20만 표본에서 식별자 2개 이상이
28.17% 나오는데, 표본을 열어 보면 대부분 한 종목을 두 방식으로 적은 것이다.

    26.2.2 JB우리캐피탈 502-5(AA-)팔자   <- 만기일 + 발행체회차, 종목은 하나

그렇다고 동사만 세도 안 된다. 동사 2개가 5.43% 인데 이쪽도 대부분 한 종목이다.

    29.1.9(화) 신한캐피탈 (민3.703, 끝.17, AA-) 팔자...민팔자   <- 되풀이

그래서 둘을 겹친다.

    **종목 앵커가 새로 나오되, 직전 앵커 이후에 이미 매매 동사가 있었으면
    거기서 다리가 끊긴다.**

앵커 = 만기일(25.6.12) | 발행체회차(신한캐피탈429-4) | 지표코드(23-7).
첫 앵커 앞의 머리말은 모든 다리에 공통이므로 각 다리 앞에 다시 붙인다
(`<A0 여전채팔자>`, `[50억]` 같은 것이 여기 온다).

## 검증한 모양

    25.1.10 신한CD 50억 팔자 25.6.12 신한CD 50억 팔자 25.9.25 우리 CD 50억 팔자   -> 3
    23-7 사고 23-2 팔자 역전 -0.8비피 교체                                        -> 2  (교체)
    29.3.4 한국전력980 팔자 (민3.738 끝5 쿠2.158) 21-5 1억 팔자                   -> 2  (M1 원례)
    26.2.2 JB우리캐피탈 502-5(AA-)팔자 /민 3.47 (끝전 33)..                       -> 1
    29.1.9(화) 신한캐피탈 (민3.703, 끝.17, AA-) 팔자...민팔자                      -> 1

## 산출물

`kbond_legs.parquet` — 다리가 2개 이상인 메시지만 담는다. 다리 1개짜리는
본 표(`kbond_structured_data.parquet`)가 이미 정확하므로 중복해 담지 않는다.
본 표는 손대지 않는다. 조인 키는 (Room, Date, Time, Sender).
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from parse_kbond_logs import (COLUMNS, NAME_STOPWORDS, PA_SCHEMA, RE_BOND_CODE,
                              RE_BOND_CODE_1, RE_BUY, RE_MATURITY_SP, RE_SELL,
                              broker_key, sender_key,
                              RE_BOND_NAME, RE_MATURITY, RE_TB_PREFIX,
                              extract, split_broker)

BASE = Path(r"C:\Users\infomax\Projects\data\kbond")
PARQUET = BASE / "kbond_structured_data.parquet"
OUT = BASE / "kbond_legs.parquet"
# 2026-09-01 예약 태스크 회차가 재생성 도중 죽어 OUT 이 footer 없이 잘렸다.
# 임시파일에 다 쓴 뒤에만 갈아끼운다.
TMP = BASE / "kbond_legs.parquet.tmp"
CHUNK = 500_000

# 매매 동사. 이게 나온 뒤의 새 앵커부터 다리가 갈린다.
# ★2026-09-01 감사: 어휘를 여기 따로 적어 두었더니 파서의 동사 확장
# (추팔·파는·삽니다)이 분할기에 이식되지 않아 1,494 다리가 과소분할됐다.
# 파서에서 유도해 한 벌로 둔다 — 다음 수리 때 또 잃지 않게.
RE_VERB = re.compile(RE_SELL.pattern + "|" + RE_BUY.pattern)
# 표기 순서가 두 갈래다.
#   (가) 만기일 먼저 :  25.10.10(금) 엠캐피탈328-2 (민5.876) 팔자
#   (나) 이름 먼저   :  한국서부발전48-2 [26.4.29 수 민2.836] 팔자
# (나) 를 앵커에서 그냥 자르면 이름이 앞 다리에 붙는다(실측: '한국전력1425' 가
# 앞 다리로 가고 그 다리가 '광주광역시지방채' 를 물어 섹터가 지방채로 뒤집혔다).
# 그래서 직전 동사와 다음 앵커 사이를 본다. 거기 값이 없고 낱말만 있으면
# 그 낱말부터가 새 다리다. 값이 있으면(민/끝/3.216) 앞 다리 것이므로 앵커에서 자른다.
RE_PRICEISH = re.compile(r'민|끝|쿠|표면|%|\d\.\d')
RE_WORD = re.compile(r'[가-힣A-Za-z][가-힣A-Za-z0-9]+')

LEG_COLUMNS = ["Room", "Date", "Time", "Sender", "LegIndex", "LegCount",
               "LegText"] + [c for c in COLUMNS
                             if c not in ("Room", "Date", "Time", "Sender")]

# T6. 전부 결측인 컬럼은 행그룹마다 null 타입으로 추론돼 cast 가 깨진다
# (실측: large_string -> null). 스키마를 못 박고 매 행그룹 cast 한다.
# ★2026-09-03: 본표 열의 타입을 여기 따로 베껴 두었더니 파서에 AtMP 열이 붙은 날
# 다리표가 import 부터 죽었다(KeyError). 본표 열의 유일한 출처는 파서의 PA_SCHEMA 다 —
# 다리 고유 3열만 여기 적는다. 파서에 열이 늘면 다리표도 같이 는다.
_TYPES = {f.name: f.type for f in PA_SCHEMA}
_TYPES.update({"LegIndex": pa.int32(), "LegCount": pa.int32(), "LegText": pa.string()})
LEG_SCHEMA = pa.schema([(c, _TYPES[c]) for c in LEG_COLUMNS])
assert set(LEG_COLUMNS) == set(_TYPES), "LEG_COLUMNS 와 타입표 불일치"


def anchors(body: str) -> list[int]:
    """종목 앵커의 시작 위치. 중복 위치는 하나로 접는다."""
    pos = set()
    for m in RE_MATURITY.finditer(body):
        pos.add(m.start())
    for m in RE_MATURITY_SP.finditer(body):     # 공백 구분 만기(파서와 동일)
        pos.add(m.start())
    for m in RE_BOND_CODE_1.finditer(body):     # 한 자리 회차
        pos.add(m.start())
    for m in RE_BOND_CODE.finditer(body):
        pos.add(m.start())
    for m in RE_BOND_NAME.finditer(body):
        if m.group(1) not in NAME_STOPWORDS:
            pos.add(m.start())
    return sorted(pos)


# 값+동사 쌍이 둘 이상인 양방향 호가. 슬래시·쉼표·공백 어느 구분자든 받는다.
RE_SIDE = re.compile(
    r'[^/,]*?\d[\d.]*\s*%?\s*[^/,]{0,12}?(?:팔자|사자|매도|매수)[^/,]{0,8}')


def _mask_parens(body: str) -> str:
    """괄호 안을 가린다(길이는 그대로). 조각이 괄호 안에서 시작하는 것을 막는다."""
    out, depth = [], 0
    for ch in body:
        if ch in "([{":
            depth += 1
            out.append(ch)
        elif ch in ")]}":
            depth = max(0, depth - 1)
            out.append(ch)
        else:
            out.append(" " if depth else ch)
    return "".join(out)


def _split_two_sided(body: str):
    """한 종목에 양쪽 호가가 다 적힌 줄을 (머리말, 다리들) 로 쪼갠다. 아니면 (None, []).

    ★[OWNER 2026-09-09] 예전에는 조각이 괄호 안에서 시작하면 **분해를 포기**했다
      (2026-09-01 감사: 'AA-) 팔자' 처럼 잘려 다리 16,301개의 짝이 깨졌다).
      그런데 그 포기 때문에 «(민평 3.665%/ 끝.45/ AAA) 오버6.5팔자동/오버7사자동» 처럼
      **괄호 뒤에 양면이 오는** 줄이 통째로 SWAP 한 줄이 됐다.
      포기하는 대신 **괄호 안을 가려 놓고** 조각을 찾는다 — 그러면 조각이 괄호 안에서
      시작할 수가 없고, 괄호 짝도 안 깨진다. 종목명·민평은 머리말로 보존된다.
    """
    masked = _mask_parens(body)
    ms = list(RE_SIDE.finditer(masked))
    if len(ms) < 2:
        return None, []
    # ★★매치 구간을 **다리 본문으로 쓰면 안 된다.** `RE_SIDE` 는 동사 뒤를 8자만 물어서
    #   결과금리가 반토막 난다(실측: 「팔자+3원  3.267%」 -> 「팔자+3원  3.2」).
    #   그러면 그 다리는 문면 금리를 잃고 «원 환산» 으로 떨어져 값이 달라진다
    #   (verify [F2c] 가 잡았다 — 롯데카드540-1 conv 3.275 대 문면 3.267).
    #   매치는 **자를 자리**로만 쓰고, 본문은 자리 사이를 통째로 잘라 준다.
    cuts = [m.start() for m in ms]
    pieces = [body[a:b] for a, b in zip(cuts, cuts[1:] + [len(body)])]
    sides = {"S" if RE_SELL.search(x) else "B" for x in pieces}
    if len(sides) < 2:                            # 양쪽이 다 있어야 다리다
        return None, []
    head = body[:cuts[0]].strip()                 # 종목명은 머리말로 보존한다
    return head, [x.strip() for x in pieces]


def split_legs(message: str):
    """(브로커, 머리말, 다리 본문 목록). 다리가 하나면 목록 길이 1."""
    broker, body = split_broker(message)
    body = RE_TB_PREFIX.sub(r'\1 ', body)
    ap = anchors(body)
    if not ap:
        # ★2026-09-01 감사: 종목이 하나여도 한 줄에 매수·매도가 다 적힌
        # 양방향 호가가 62,395행 있는데(‘3.70% 팔자 /3.75% 사자’) 본표는
        # Position 이 스칼라라 전량 단일 SELL 로 접힌다. 앵커가 없어도
        # **값+동사 쌍이 둘 이상이면** 다리로 쪼갠다.
        h2, two = _split_two_sided(body)
        return (broker, h2, two) if two else (broker, "", [body])
    # ★[OWNER 2026-09-09 「두 다리로 갈라 책에 올린다」] 앵커가 **있어도** 양면일 수 있다.
    #   예전에는 앵커가 없을 때만 양면 분할을 시도해서, 종목 이름이 적힌 양면 호가가
    #   통째로 SWAP 한 줄이 됐다(실측 28,442행 — 사자 다리의 레벨이 버려졌다):
    #     오버6.5팔자동/오버7사자동
    #     100억 팔자 +14원 2.709% /+8원사자 2.814%
    #   앵커가 하나뿐이면(= 종목이 하나) 양면 분할을 덧대어 본다.
    if len(ap) == 1:
        h2, two = _split_two_sided(body)
        if len(two) > 1:
            return broker, h2, two

    head = body[:ap[0]].strip()
    cuts = [ap[0]]
    for p in ap[1:]:
        vs = list(RE_VERB.finditer(body[cuts[-1]:p]))
        if not vs:                               # 직전 다리에 동사가 아직 없다
            continue
        vend = cuts[-1] + vs[-1].end()
        cut = p
        mid = body[vend:p]
        if not RE_PRICEISH.search(mid):
            w = RE_WORD.search(mid)
            if w:
                _cut = vend + w.start()
                # ★2026-09-01 감사: 이 보정이 괄호 안에서 잘라 33,286 다리의
                # 괄호 짝이 깨졌다. 컷 자리가 괄호 안이면 보정을 포기한다.
                if body[:_cut].count("(") - body[:_cut].count(")") <= 0:
                    cut = _cut
        cuts.append(cut)
    cuts.append(len(body))
    legs = [l for l in (body[cuts[i]:cuts[i + 1]].strip()
                        for i in range(len(cuts) - 1)) if l]
    # 앵커가 있어도 다리가 하나로 끝나면 양방향 호가일 수 있다
    # ('한국전력(25.10.15, 민3.685%) 3.70% 팔자 / 3.75% 사자' — 종목은 하나, 호가는 둘).
    if len(legs) == 1:
        h2, two = _split_two_sided(legs[0])
        if two:
            return broker, (head + " " + (h2 or "")).strip(), two
    return broker, head, legs


def main() -> int:
    if not PARQUET.exists():
        sys.exit(f"[FATAL] 없음: {PARQUET}")
    t0 = time.time()
    src = pq.ParquetFile(PARQUET)
    cols = ["Room", "Date", "Time", "Sender", "Message", "MsgType", "SourceFile"]

    writer = None
    n_msg = n_multi = n_leg = 0
    hist: dict[int, int] = {}
    try:
        for rg in range(src.num_row_groups):
            df = src.read_row_group(rg, columns=cols).to_pandas()
            # 2026-09-01: QUOTE 만 보던 것을 전 유형으로 넓혔다.
            # CONFIRM(체결 신호 16.6만)·INQUIRY 에도 여러 종목을 한 줄에 적는다.
            # MsgType 은 열로 남으므로 하류가 가려 쓴다.
            df = df[df["Message"].notna()]
            rows = []
            for r in df.itertuples(index=False):
                n_msg += 1
                broker, head, legs = split_legs(str(r.Message))
                hist[len(legs)] = hist.get(len(legs), 0) + 1
                if len(legs) < 2:
                    continue
                n_multi += 1
                for i, leg in enumerate(legs):
                    text = f"{head} {leg}".strip() if head else leg
                    rec = {"Room": r.Room, "Date": r.Date, "Time": r.Time,
                           "Sender": r.Sender, "LegIndex": i,
                           "LegCount": len(legs), "LegText": leg,
                           "Message": str(r.Message), "SourceFile": r.SourceFile,
                           "Timestamp": pd.NaT}
                    rec.update(extract(text, r.Date.strftime("%Y%m%d")
                                       if pd.notna(r.Date) else None))
                    # ★2026-09-01 감사: 분할기가 브로커를 통째로 버려
                    # 다리표 Broker 가 470,120/470,124 결측이었다.
                    if rec.get("Broker") is None and broker:
                        rec["Broker"] = broker
                        rec["BrokerKey"] = broker_key(broker)
                    rec["SenderKey"] = sender_key(r.Sender)
                    # ★교체 다리의 방향이 SWAP 으로 뭉개져 88,888 다리가
                    # 방향을 잃었다. 다리 자신의 텍스트에 방향어가 한쪽뿐이면
                    # 그 방향이 이 다리의 방향이다(메시지 전체는 교체여도).
                    if rec.get("Position") == "SWAP":
                        _s = bool(RE_SELL.search(leg))
                        _b = bool(RE_BUY.search(leg))
                        if _s != _b:
                            rec["Position"] = "SELL" if _s else "BUY"
                            rec["PositionSource"] = "leg"
                    rows.append(rec)
                    n_leg += 1
            if not rows:
                continue
            out = pd.DataFrame(rows).reindex(columns=LEG_COLUMNS)
            out["Timestamp"] = pd.to_datetime(
                out["Date"].dt.strftime("%Y%m%d") + " " + out["Time"],
                format="%Y%m%d %H:%M:%S", errors="coerce")
            for c in ("OddLot", "AmountImplied", "IsInquiry"):
                out[c] = out[c].astype("boolean")
            out["LegIndex"] = out["LegIndex"].astype("int32")
            out["LegCount"] = out["LegCount"].astype("int32")
            tbl = pa.Table.from_pandas(out, preserve_index=False).cast(LEG_SCHEMA)
            if writer is None:
                writer = pq.ParquetWriter(TMP, LEG_SCHEMA, compression="zstd")
            writer.write_table(tbl)
            print(f"  행그룹 {rg + 1}/{src.num_row_groups}  다리 누적 {n_leg:,}",
                  flush=True)
    except BaseException:
        # 중간에 죽으면 잘린 조각만 버리고 직전 산출물을 그대로 둔다.
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

    print("\n" + "=" * 66)
    print(f"  메시지 전체         {n_msg:,}")
    print(f"  다리 2개 이상       {n_multi:,}  ({100 * n_multi / max(n_msg, 1):.2f}%)")
    print(f"  펼친 다리 행수      {n_leg:,}")
    print("\n  메시지당 다리 수 분포")
    for k in sorted(hist)[:10]:
        print(f"    {k:>2}개 {hist[k]:>9,}  ({100 * hist[k] / max(n_msg, 1):5.2f}%)")
    print(f"\n  -> {OUT}  ({OUT.stat().st_size / 2**20:,.1f} MB)   {time.time() - t0:,.0f}초")
    return 0


if __name__ == "__main__":
    sys.exit(main())
