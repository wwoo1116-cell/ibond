"""언제부터 믿을 수 있나 — 30분 격자.

세 가지를 잰다.
  (1) 시계 기준 정확도      : 시각별 |추정 - 마감민평|
  (2) 책 상태 기준 정확도   : 그때까지 호가 난 종목 수 / 자기 호가 유무로 갈라서
  (3) 수렴                  : 그 시각 추정이 장 끝 추정과 얼마나 다른가
"""
import os, numpy as np, pandas as pd
from sqlalchemy import create_engine, text
from train3 import loo_wmedian_curve, wmedian

PARQ = r"C:\Users\infomax\Projects\data\kbond\kbond_structured_data.parquet"
GRID = ["09:30","10:00","10:30","11:00","11:30","12:00","12:30","13:00",
        "13:30","14:00","14:30","15:00","15:30","15:45","16:00","16:15","16:30","17:00","18:00"]
HALF = 0.25


def eng():
    u,p,h,q = os.environ['BW_MYSQL_USER'],os.environ['BW_MYSQL_PASSWORD'],os.environ['BW_MYSQL_HOST'],os.environ['BW_MYSQL_PORT']
    return create_engine(f"mysql+pymysql://{u}:{p}@{h}:{q}/infomax?charset=utf8mb4")


def norm(s): return s.str.replace(r'^(\d{2})-0*(\d+)$', r'\1-\2', regex=True)


with eng().connect() as c:
    mp = pd.read_sql(text("SELECT 일자 d,종목코드 k,민평 y FROM `국고통_민평` "
                          "WHERE 일자>='2023-11-01' AND LEFT(종목코드,4)='KR10'"), c)
    iss = pd.read_sql(text("SELECT 표준코드 k,종목명 c,만기일 m FROM `국채_발행정보` "
                           "WHERE 종목명 REGEXP '^[0-9]{1,2}-[0-9]{1,2}$'"), c)
iss["c"] = norm(iss.c)
mp = mp.merge(iss.drop_duplicates("k")[["k","c"]], on="k")
piv = mp.pivot_table(index="d", columns="c", values="y").sort_index()
prev = piv.shift(1)
mat = dict(zip(iss.c, pd.to_datetime(iss.m)))

cols=["Date","Time","Sector","BondCode","Position","QuoteYield","MsgType"]
df = pd.read_parquet(PARQ, columns=cols)
g = df[(df.Sector=="국고") & df.BondCode.notna() & df.QuoteYield.notna()
       & df.MsgType.eq("QUOTE") & df.Position.isin(["SELL","BUY"])].copy()
g["c"]=norm(g.BondCode); g["d"]=pd.to_datetime(g.Date)
yest = prev.stack().rename_axis(["d","c"]).rename("yest")
today = piv.stack().rename_axis(["d","c"]).rename("today")
g = g.join(yest, on=["d","c"]).dropna(subset=["yest"])
g["bp"]=(g.QuoteYield-g.yest)*100
g = g[g.bp.abs()<100].sort_values(["d","c","Time"])
print(f"호가 {len(g):,}  영업일 {g.d.nunique()}  종목 {g.c.nunique()}")

rows=[]
for cut in GRID:
    s = g[g.Time < cut]
    if not len(s): continue
    gb = s.groupby(["d","c"])
    f = pd.DataFrame({"q_n": gb.size()})
    for side,tag in (("SELL","off"),("BUY","bid")):
        f[tag] = s[s.Position==side].groupby(["d","c"]).bp.last()
    f["m_est"] = f[["off","bid"]].mean(axis=1)
    only_o = f.off.notna()&f.bid.isna(); only_b = f.bid.notna()&f.off.isna()
    f.loc[only_o,"m_est"] = f.off[only_o]+HALF
    f.loc[only_b,"m_est"] = f.bid[only_b]-HALF
    f["both"] = f[["off","bid"]].notna().all(axis=1).astype(int)
    f = f.reset_index()
    f["ttm"] = [ (mat[c]-d).days/365.25 if c in mat else np.nan for d,c in zip(f.d,f.c) ]
    f = f[f.ttm.between(0.05,31)].sort_values(["d","ttm"]).reset_index(drop=True)
    f["w"] = np.where(f.both==1,1.0,0.45)
    cv,_ = loo_wmedian_curve(f.d.values, f.ttm.values.astype(float),
                             f.m_est.values.astype(float), f.w.values.astype(float))
    f["cv"]=cv
    f["nmkt"] = f.groupby("d")["c"].transform("size")          # 그때까지 호가 난 종목 수
    f["est"] = np.where(f.both==1, 0.5*f.m_est+0.5*f.cv, f.cv)
    f["est"] = np.where(f.est.isna(), f.cv, f.est)
    f = f.join(today, on=["d","c"]).dropna(subset=["today","est"])
    f["y"]  = (f.today - f.yest_x if "yest_x" in f else np.nan)
    f["yv"] = [ prev.at[d,c] if (d in prev.index and c in prev.columns) else np.nan for d,c in zip(f.d,f.c) ]
    f["y"]  = (f.today - f.yv)*100
    f = f.dropna(subset=["y"])
    f["err"] = (f.est - f.y).abs()
    f["cut"] = cut
    rows.append(f[["cut","d","c","ttm","q_n","both","nmkt","m_est","cv","est","y","err"]])
P = pd.concat(rows, ignore_index=True)
P.to_parquet("timing_panel2.parquet", index=False)
print("패널", len(P), "행 저장")
