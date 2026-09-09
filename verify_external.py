# -*- coding: utf-8 -*-
"""★파싱 정확도의 «외부» 검정 — 체결 테이프를 장외 체결 원자료와 맞춘다.

## 왜 이게 검정인가

우리 테이프는 **채팅에서 읽은 것**이고 `kbond.CFT_daily_체결호가` 는 **별개 경로로
들어온 장외 체결**이다. 두 자료는 서로를 안 본다. 그래서 값이 맞으면 그건 파서가
문면을 제대로 읽었다는 독립 증거가 된다.

기존 검정들과 무엇이 다른가:

    verify_v4 [A]   원문을 다시 파싱해 책과 대조   — 같은 파서를 두 번 쓴다
    gate_meaning [J] 뜻이 맞나(민평에 팔자 -> 체결)  — 결과검정이지 값 검정이 아니다
    verify_v4 [F2]  민평·끝전·스프레드 내부 항등식    — 자기 안에서 닫힌다
    **이 파일**      **바깥 자료와 값을 맞춘다**      — 파서가 못 보는 축

## 키를 무엇으로 잡나

(날짜, 발행체 정본, 회차). 외부의 `isin_nm` 은 «롯데캐피탈 387-2» 처럼 발행체와
회차를 같이 싣는다. 발행체는 `kbond_issuer` 로 정본화해서 맞춘다.

⚠ 외부의 `due_dt` 는 **0.6% 만 유효한 날짜**다(«010000»·«2002-00-05» 같은 값이
  대부분). 만기를 키에 넣으면 매칭이 0 이 된다 — 실측으로 확인했다.
⚠ 외부는 105일치(2024-01-31~2025-12-10)뿐이고 장외 자기매매가 대부분이라
  겹치는 표본이 작다. 「몇 건이 맞았나」가 아니라 「맞은 것들이 얼마나 가까운가」를 본다.

## 방향은 이 검정으로 못 본다

외부의 `sell_buy_tcd` 는 **보고한 쪽** 기준이고 우리 방향은 **호가를 낸 쪽** 기준이라,
같은 거래에서 서로 반대로 적힌다. 방향 검정은 `verify_v4 [I]`(귀속에 안 쓴 축)가 맡는다.

실행:  python verify_external.py
"""
import os, re, sys, collections
sys.path.insert(0, r"C:\Users\infomax\Projects\apps\kbond")
import pandas as pd, pyarrow.parquet as pq
from sqlalchemy import create_engine, text
import kbond_issuer as K
RE_SER = re.compile(r"(\d{1,4})\s*-\s*(\d{1,3})\s*$")

def key_of(name):
    s = re.sub(r"\s+", "", str(name))
    m = RE_SER.search(s)
    if not m:
        return None
    head = s[:m.start()]
    canon = K.canon_issuer(head)[0]
    return (canon, f"{int(m.group(1))}-{int(m.group(2))}")

e = create_engine(f"mysql+pymysql://{os.environ['BW_MYSQL_USER']}:{os.environ['BW_MYSQL_PASSWORD']}@{os.environ['BW_MYSQL_HOST']}:{os.environ['BW_MYSQL_PORT']}/kbond?charset=utf8mb4")
with e.connect() as c:
    cft = pd.read_sql(text("SELECT deal_date, isin_nm, credit, tr_ern_r, tr_q, sell_buy_tcd "
                           "FROM CFT_daily_체결호가 WHERE tr_ern_r > 0"), c)
cft["d"] = cft.deal_date.astype(str).str[:10]
idx = collections.defaultdict(list)
nk = 0
for d, nm, y, q, sb, cr in zip(cft.d, cft.isin_nm, cft.tr_ern_r.astype(float),
                               cft.tr_q, cft.sell_buy_tcd, cft.credit):
    k = key_of(nm)
    if k is None: continue
    nk += 1
    idx[(d, k[0], k[1])].append((y, q, sb, cr))
DAYS = set(cft.d.unique())
print(f"외부 체결 {len(cft):,}건 중 회차가 읽힌 것 {nk:,} · 칸 {len(idx):,} · {len(DAYS)}일")

fills = pq.ParquetFile(r"C:\Users\infomax\Projects\data\kbond\kbond_fills.parquet").read().to_pandas()
fills["d"] = fills["Date"].astype(str).str[:10]
sub = fills[fills.d.isin(DAYS) & fills["QuoteYield"].notna() & fills["BondName"].notna()]
hit = collections.Counter(); gaps = []; side_ok = side_n = 0
for d, bn, y, ps in zip(sub.d, sub["BondName"], sub["QuoteYield"].astype(float), sub["Position"]):
    k = key_of(bn)
    if k is None:
        hit["우리 쪽 회차 없음"] += 1; continue
    cands = idx.get((d, k[0], k[1]))
    if not cands:
        hit["외부에 그 칸이 없음"] += 1; continue
    g = min(abs(y - x[0]) * 100 for x in cands)
    gaps.append(g)
    hit["<=0.1bp" if g <= 0.1 else "<=1bp" if g <= 1 else "<=5bp" if g <= 5 else ">5bp"] += 1
    best = min(cands, key=lambda x: abs(y - x[0]))
    if ps in ("BUY", "SELL") and best[2] in ("매수", "매도"):
        side_n += 1
        side_ok += int((ps == "BUY") == (best[2] == "매수"))
tot = sum(hit.values())
print(f"\n겹치는 날의 우리 체결(금리+종목명) {tot:,}건")
for k in ["<=0.1bp","<=1bp","<=5bp",">5bp","외부에 그 칸이 없음","우리 쪽 회차 없음"]:
    v = hit.get(k, 0)
    if v: print(f"  {k:20s} {v:7,}  {v/tot*100:5.1f}%")
m = len(gaps)
if m:
    s = pd.Series(gaps)
    print(f"\n★ 외부에 같은 (날짜·발행체·회차) 가 있는 {m:,}건")
    print(f"   금리 1bp 안 {int((s<=1).sum()):,} ({(s<=1).mean()*100:.1f}%) · "
          f"0.1bp 안 {(s<=0.1).mean()*100:.1f}%")
    print(f"   |Δ| 중앙 {s.median():.3f}bp · p90 {s.quantile(.9):.2f} · p99 {s.quantile(.99):.2f}")
    if side_n:
        print(f"   방향 일치 {side_ok:,}/{side_n:,} ({side_ok/side_n*100:.1f}%)")
