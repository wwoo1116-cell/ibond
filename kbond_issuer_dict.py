# -*- coding: utf-8 -*-
"""발행체 표제어 사전 굽기 [OWNER 2026-09-09 「4까지 · 정본 한국산업은행」].

## 왜 이름이 아니라 «분류» 를 키로 잡는가

산금 진단에서 나온 것: 벤더 원장도 이름이 갈라져 있다. 같은 KR3102* 에

    infomax_bond.issuer   한국산업은행 571 · KDB산업은행 271
    bond_info.issuer      산업은행 428

두 표의 공통 ISIN 20,569건에서 issuer 문자열 일치율은 **59.8%** 다. 이름을
이름으로 맞추면 원장 스스로 셋으로 갈라진다.

안 갈라진 것은 «분류» 다. `cclass`(=`bond_info.small`)는 벤더가 정규화한
발행체 키이고 법인명 이형태를 이미 접어 둔다:

    KB캐피탈    <- {KB캐피탈, 케이비캐피탈, 케이비캐피탈(주)}
    IBK기업은행  <- {IBK기업은행, 중소기업은행}
    SC제일은행   <- {(주)한국스탠다드차타드은행, SC제일은행, 한국스탠다드차타드은행}

## cclass 가 늘 발행체인 것은 아니다

    금융채 12,311   cclass = 발행체 (KDB산업은행·하나캐피탈·신한카드…)  63종
    공사공단채 6,381 cclass = 발행체 (한국전력공사·한국도로공사…)        48종
    지방채  1,737   cclass = 발행체 (부산광역시·경기도…)                24종
    회사채 20,711   cclass = **범주** (회사채(일반)·무보증 AAA…)  -> issuer 를 쓴다

꼬리가 «기타» 인 cclass 도 범주다 — «기타금융채 기타» 안에 무궁화캐피탈·
에코캐피탈·영남종합금융·중앙종합금융·큐더스벤처스 다섯이 들었다(실측).

## 은어는 어디서 오나 — 종목명 머리말

★이게 이번 레인의 수확이다. 벤더 종목명이 데스크 은어를 **그대로** 쓴다.

    산금23신할0100-0904-1  -> 머리말 «산금»  -> cclass KDB산업은행 (n=1,239 · 100%)
    농금채…                -> 머리말 «농금채» -> 농협중앙회        (n=  181 · 100%)

종목명 머리말 8,045종 중 **7,058종(87.7%)이 단일 cclass 로만** 간다. 손으로
넣던 별칭의 대부분이 판정이 아니라 자료였다.

## 세 층 — 층마다 «왜 접었나» 가 다르다

    master   원장이 말한 것    cclass·issuer·종목명 머리말
    mp-test  검정이 통과시킨 것  같은 날·같은 회차·같은 만기 |Δ민평| <= 1bp, n >= 5
    owner    사람이 판정한 것    회차를 안 달고 다니는 은어(한전·농중·도공·예특)

산출: kbond_issuer_dict.json
      {표제어: {"variants": [...], "sector": [aclass, bclass], "src": ...}}
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

OUT = Path(__file__).parent / "kbond_issuer_dict.json"

_ISSUER_CCLASS = {"금융채", "공사공단채", "지방채"}
_RE_CCLASS_BUCKET = re.compile(r"기타$|^회사채|^무보증|^전환사채|^신주인수권|^\d+Y$|^국민주택")
# ★[2026-09-09 3차] 벤더 `issuer` 열에도 **범주가 섞여 있다.** 실측: 원장 9,223행이
#   「무보증 A+」(3,533)·「무보증 AA-」(1,976)·「기타 국채」(1,167) 를 발행체로 달고
#   있었다. cclass 만 거르고 issuer 는 안 걸러서 범주가 표제어로 승격됐다.
#   이건 발행체가 아니다 — 사전에서 빼면 raw 로 남고, 그게 정직하다.
_RE_ISSUER_BUCKET = re.compile(
    r"^무보증|^회사채|^기타|기타$|^전환사채|^신주인수권|^\d+Y$|^국민주택|"
    r"^개인투자용|^교환사채")
_RE_CORP = re.compile(r"\(주\)|주식회사|㈜|\(유\)|유한회사|\s+")
# 표제어 표시형 — 법인격만 떼고 원래 띄어쓰기는 살린다('주식회사 에스파워' -> '에스파워').
_RE_CORP_DISP = re.compile(r"^\s*(?:\(주\)|주식회사|㈜|\(유\)|유한회사)\s*|"
                           r"\s*(?:\(주\)|주식회사|㈜|\(유\)|유한회사)\s*$")
# 종목명 머리말 — 법인격을 먼저 벗기고 앞쪽 한글/영문 덩어리를 문다.
_RE_STEM = re.compile(r"^([가-힣A-Za-z][가-힣A-Za-z&.]*)")
# 한 글자 머리말은 못 쓴다('주'·'S'). 두 글자부터.
_STEM_MIN = 2

# ★[OWNER 2026-09-09] 정본 덮어쓰기 — 벤더 cclass 를 그대로 안 쓰는 자리.
#   「산금의 정본은 한국산업은행」 판정.
CANON_OVERRIDE = {
    "KDB산업은행": "한국산업은행",
}


def disp(s):
    """표제어 표시형 — 앞뒤 법인격 표기를 뗀다. 가운데 것은 안 건드린다."""
    out = _RE_CORP_DISP.sub("", str(s)).strip()
    return out or str(s).strip()


def norm(s):
    """이형태 대조용 정규화 — 법인격·공백만 벗긴다. 대소문자는 살린다
    (원장이 구별한다: 'kb캐' 와 'KB캐' 가 다른 행으로 산다)."""
    return _RE_CORP.sub("", str(s)).strip()


def stem(s):
    m = _RE_STEM.match(norm(s))
    w = m.group(1) if m else None
    return w if w and len(w) >= _STEM_MIN else None


def engine(db="kbond"):
    need = ["BW_MYSQL_USER", "BW_MYSQL_PASSWORD", "BW_MYSQL_HOST", "BW_MYSQL_PORT"]
    miss = [k for k in need if not os.environ.get(k)]
    if miss:
        sys.exit(f"[FATAL] 환경변수 미설정: {miss}")
    return create_engine(
        f"mysql+pymysql://{os.environ['BW_MYSQL_USER']}:{os.environ['BW_MYSQL_PASSWORD']}"
        f"@{os.environ['BW_MYSQL_HOST']}:{os.environ['BW_MYSQL_PORT']}/{db}?charset=utf8mb4",
        pool_pre_ping=True)


def load_master():
    with engine().connect() as c:
        a = pd.read_sql(text("SELECT isin, isin_nm, issuer, aclass, bclass, cclass "
                             "FROM infomax_bond"), c)
        b = pd.read_sql(text("SELECT isin, isin_nm, issuer, big, mid, small "
                             "FROM bond_info"), c)
    b = b.rename(columns={"big": "aclass", "mid": "bclass", "small": "cclass"})
    return pd.concat([a, b], ignore_index=True)


def build(df=None):
    df = load_master() if df is None else df
    df = df[df.aclass.notna() & df.cclass.notna() & df.issuer.notna()].copy()
    out = {}

    def add(canon, variant, sector, src):
        canon = CANON_OVERRIDE.get(canon, disp(canon))
        e = out.setdefault(canon, {"variants": set(), "sector": sector, "src": src})
        v = norm(variant)
        if v and v != norm(canon):
            e["variants"].add(v)
        return canon

    # 종목이 어느 표제어의 것인지 먼저 정한다 — cclass 가 발행체면 cclass, 아니면 issuer.
    is_iss = df.aclass.isin(_ISSUER_CCLASS) & ~df.cclass.str.contains(_RE_CCLASS_BUCKET)
    df["key"] = df.cclass.where(is_iss)
    rest = df[~is_iss]
    if len(rest):
        # 범주 대분류는 issuer 의 «최다 사용형» 을 표제어로 삼는다.
        top = rest.groupby(rest.issuer.map(norm))["issuer"].agg(lambda s: s.value_counts().idxmax())
        df.loc[~is_iss, "key"] = rest.issuer.map(norm).map(top)
    df = df[df.key.notna() & (df.key.astype(str).str.len() > 0)]
    # ⚠ issuer 가 범주인 행은 통째로 뺀다 — 발행체가 아니다.
    df = df[~df.key.astype(str).str.contains(_RE_ISSUER_BUCKET)]

    # (1) 원장층 — 표제어와 법인명 이형태
    #
    # ⚠ 표제어는 다른 표제어의 이형태가 될 수 없다. 벤더는 지방채를 «발행체» 가 아니라
    #   «채권 프로그램» 으로 나눈다 — 서울도시철도채권의 issuer 가 «서울특별시» 라서,
    #   그대로 두면 표제어 「서울특별시」가 「서울도시철도」의 이형태로 빨려 들어간다
    #   (실측: 서울특별시채권 -> 서울도시철도). 덜 합치는 쪽으로 틀리는 게 안전하다.
    #
    # ★보호는 **cclass 에서 온 표제어만** 받는다. issuer 에서만 온 이름까지 지키면
    #   개명을 못 따라간다 — 산은캐피탈은 issuer 이고 cclass 는 KDB캐피탈이라
    #   접혀야 맞다(반대로 서울특별시는 bond_info 의 cclass 라 지켜야 맞다).
    heads = {norm(CANON_OVERRIDE.get(k, disp(k)))
             for k in df.loc[is_iss.reindex(df.index, fill_value=False), "key"].unique()}
    for key, g in df.groupby("key"):
        ac, bc = g.aclass.iloc[0], g.bclass.iloc[0]
        canon = add(key, key, (ac, bc), "master")
        for iss in g.issuer.unique():
            if norm(iss) in heads and norm(iss) != norm(canon):
                continue
            add(key, iss, (ac, bc), "master")

    # (2) 원장층 — 종목명 머리말. **단일 표제어로만 가는 것만** 받는다.
    #     ⚠ 이 «단일» 조건이 안전장치다. 빼면 «신보»(5 표제어)·«중진공»(10)이
    #       한 발행체로 접힌다.
    st = df.assign(stem=df.isin_nm.map(stem)).dropna(subset=["stem"])
    g = st.groupby("stem")["key"].agg(k="nunique", top=lambda s: s.iloc[0], n="size")
    ok = g[(g.k == 1) & (g.n >= 1)]
    for s, r in ok.iterrows():
        if norm(s) in (norm(x) for x in out):     # 이미 표제어면 이형태로 안 넣는다
            continue
        add(r.top, s, out.get(CANON_OVERRIDE.get(r.top, r.top), {}).get("sector"), "master")

    return {k: {"variants": sorted(v["variants"]),
                "sector": list(v["sector"]) if v["sector"] else None,
                "src": v["src"]}
            for k, v in sorted(out.items())}


if __name__ == "__main__":
    d = build()
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    nv = sum(len(v["variants"]) for v in d.values())
    print(f"표제어 {len(d):,} · 이형태 {nv:,}  -> {OUT}")
    for k in ["한국산업은행", "KB캐피탈", "IBK기업은행", "한국전력공사", "산은캐피탈",
              "농협중앙회", "한국도로공사"]:
        if k in d:
            print(f"  {k:12s} {d[k]['sector']} <- {d[k]['variants'][:8]}")
        else:
            print(f"  {k:12s} 없음")
