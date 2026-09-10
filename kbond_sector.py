# -*- coding: utf-8 -*-
"""계열 표 굽기 — 규칙을 «독립 대조» 로 검증한다 [OWNER 2026-09-09 「다 해라」].

## 무엇을 고쳤나

`_SECTOR_RULES` 는 발행체명에 키워드가 **들어 있는지** 로 계열을 정했다. 부분문자열은
남의 이름 안에 산다. 2026-09-09 하루에만 다섯이 나왔다.

    「산은」 ⊂ 부**산은**행      20,983행이 특은채로
    「제주」 ⊂ 제**주은행**        578행이 지방채로
    「산금」 ⊂ 수**산금**융      수협 계열이 특은채로
    「도」   ⊂ HL만**도**       1,645행이 지방채로   <- 이 표가 잡았다
    「뱅크」 ⊂ 현대오일**뱅크**    6,682행이 은행채로   <- 이 표가 잡았다

앞의 셋은 사람이 찾았고, 뒤의 둘은 **이 대조가** 찾았다. 그게 이 파일의 존재 이유다.

## 그래서 규칙을 버렸나 — 아니다. 둘을 붙였다

처음엔 규칙을 버리고 벤더 표로 갈아 끼우려 했다. 재 보니 표가 더 낫지도 못하지도
않았다 — **섞여 있었다.**

    표가 옳은 자리    SK가스·연합자산관리·현대오일뱅크는 회사채가 맞다(규칙이 틀렸다)
    규칙이 옳은 자리  발전 5사·도시공사·에프앤아이는 데스크 관례다(벤더는 회사채로 싣는다)

그래서 규칙은 **앵커를 붙여** 충돌을 원천봉쇄하고(`캐피탈$` · `^경기도$`), 이 표는
**독립 대조**로 남긴다. 규칙을 고칠 때마다 돌려서 «다음 부산은행» 을 사람이 아니라
대조가 찾게 한다. 지금 어긋남 **0종 0행**(의도된 14개 제외 — 아래 ACCEPTED).

## 벤더 분류가 오너 6분류로 가는 길

    금융채/은행채       -> 은행채  ★단 KDB산업은행·IBK기업은행·한국수출입은행은 특은채
    금융채/카드·기타금융채 -> 여전채
    공사공단채/일반·기타   -> 공사채  (농협중앙회·수협중앙회가 «기타» 다 — 오너 판정과 일치)
    공사공단채/지방공기업   -> 지방채
    지방채/*           -> 지방채
    회사채/*           -> 회사채  ★단 금융지주는 은행채

산출: kbond_sector.json  {표제어: 계열}  — 대조용이다. 화면은 규칙을 쓴다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

import kbond_issuer_dict as KD

OUT = Path(__file__).parent / "kbond_sector.json"

VENDOR = {
    ("금융채", "은행채"): "은행채",
    ("금융채", "카드"): "여전채",
    ("금융채", "기타금융채"): "여전채",
    ("공사공단채", "일반"): "공사채",
    ("공사공단채", "공사공단채 기타"): "공사채",
    ("공사공단채", "지방공기업"): "지방채",
    ("지방채", "지역개발채권"): "지방채",
    ("지방채", "도시철도채권"): "지방채",
    # ★[OWNER 2026-09-10] 유동화를 7번째 계열로 둔다. 벤더가 이미 갈라 놓은 축이다 —
    #   ("회사채","회사채(ABS)") 5,743행 · cclass 「무보증(ABS) AAA」 3,703 등.
    #   지금까지 ACLASS 가 aclass=회사채 를 통째로 접으면서 이 구분을 버리고 있었다.
    #   표제어 기준 3,667종이고 «둘 다 가진 것 0종» 이라 모호하지 않다.
    ("회사채", "회사채(ABS)"): "유동화",
}
ACLASS = {"회사채": "회사채", "지방채": "지방채", "공사공단채": "공사채", "기타": "회사채"}

# ★[OWNER] 특은채는 셋뿐이다 — 산금·중금·수은.
특은 = {"한국산업은행", "KDB산업은행", "IBK기업은행", "한국수출입은행"}
# ★[OWNER 6분류] 금융지주는 은행채다(벤더는 회사채로 싣는다).
RE_지주 = re.compile(r"금융지주$|^신한지주$")
# 증권사는 회사채 [OWNER 2026-09-03].
RE_증권 = re.compile(r"증권$|증권주식회사$")


def build(df=None):
    df = KD.load_master() if df is None else df
    df = df[df.aclass.notna() & df.cclass.notna() & df.issuer.notna()].copy()
    is_iss = df.aclass.isin(KD._ISSUER_CCLASS) & ~df.cclass.str.contains(KD._RE_CCLASS_BUCKET)
    df["key"] = df.cclass.where(is_iss)
    rest = df[~is_iss]
    if len(rest):
        top = rest.groupby(rest.issuer.map(KD.norm))["issuer"].agg(
            lambda s: s.value_counts().idxmax())
        df.loc[~is_iss, "key"] = rest.issuer.map(KD.norm).map(top)
    df = df[df.key.notna() & (df.key.astype(str).str.len() > 0)]
    df = df[~df.key.astype(str).str.contains(KD._RE_ISSUER_BUCKET)]

    out = {}
    for key, g in df.groupby("key"):
        canon = KD.CANON_OVERRIDE.get(key, KD.disp(key))
        ac, bc = g.aclass.iloc[0], g.bclass.iloc[0]
        sec = VENDOR.get((ac, bc)) or ACLASS.get(ac)
        if sec is None:
            continue
        if canon in 특은 or key in 특은:
            sec = "특은채"
        elif RE_지주.search(canon):
            sec = "은행채"
        elif RE_증권.search(canon) and sec not in ("여전채", "유동화"):
            sec = "회사채"
        out[canon] = sec
    return out


if __name__ == "__main__":
    import collections

    import kbond_issuer as K
    # ★[2026-09-10] `classify_issuer` 는 이제 **위험순** 을 낸다(무위험·카드채·캐피탈).
    #   대조는 «발행체 계열» 축이라 `sector_of` 를 봐야 한다. 위험 라벨과 견주면
    #   지방채·공사채가 통째로 어긋남으로 떠서 대조가 죽는다.
    from kbond_live import sector_of as classify_issuer

    tbl = build()
    OUT.write_text(json.dumps(tbl, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"계열 표 {len(tbl):,}종  -> {OUT}")
    print(collections.Counter(tbl.values()).most_common())

    # ★[OWNER] 벤더와 **일부러 다른** 자리. 데스크 관례가 벤더 분류를 이긴다.
    #   여기 적힌 것은 대조에서 뺀다 — 그래야 «새로 생긴 어긋남» 만 보인다.
    ACCEPTED = {
        # 한전 발전 자회사는 주식회사지만 데스크는 공사채로 본다
        "한국서부발전", "한국중부발전", "한국남부발전", "한국남동발전", "한국동서발전",
        "한국수력원자력",
        # 에프앤아이(부실채권 투자)는 오너 6분류에서 여전채
        "대신에프앤아이", "하나에프앤아이", "우리금융에프앤아이", "키움에프앤아이",
        # 도시공사·개발공사는 벤더가 «일반» 으로 싣지만 데스크는 지방채
        "서울주택도시공사", "대전도시공사", "전남개발공사",
        "한국해외인프라도시개발지원공사",
    }

    # 지금 규칙과 어디가 다른가 — 행 가중으로 본다
    cache = Path(__file__).parent / "artifacts" / "cr_heads.parquet"
    if cache.exists():
        rows = collections.Counter()
        for r, n in pd.read_parquet(cache)["raw"].value_counts().items():
            rows[K.canon_issuer(r)[0]] += n
        diff = collections.Counter()
        for name, n in rows.items():
            t = tbl.get(name)
            # ★[2026-09-10] 유동화 축은 대조에서 뺀다. 이름으로 못 가리는 축이라
            #   «표가 정본» 이고 규칙은 애초에 판정할 자격이 없다. 여기 두면 3,667종이
            #   통째로 어긋남으로 떠서 «새로 생긴 어긋남만 보인다» 는 이 대조의 목적이
            #   죽는다. ⚠그러니 유동화는 이 대조가 지켜 주지 않는다 — 표가 유일한 근거다.
            if t == "유동화":
                continue
            if t and name not in ACCEPTED and t != classify_issuer(name):
                diff[(classify_issuer(name), t, name)] = n
        tot = sum(diff.values())
        print(f"\n== 표로 바꾸면 달라지는 것 {len(diff):,}종 · {tot:,}행 ==")
        for (old, new, name), n in diff.most_common(25):
            print(f"  {n:8,}  {name:24s} {old} -> {new}")
