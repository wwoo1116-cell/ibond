# -*- coding: utf-8 -*-
"""범주 콜 추출 — 종목 없이 «만기대 · 섹터 · 등급» 으로 부르는 호가.

[OWNER 2026-09-02] 「신설하세요」

## 무엇이 범주 콜인가

    A급 회사채 1.5~3년 정도 매수 관심
    3개월 공사 특은 사자
    24년 3~4월 시은채 사자
    25년 말~ 26년 초 여전채/크레딧 사자  +12빕

종목 식별자(BondCode·BondName·Maturity)가 **하나도 없는데** 만기대와 범주로
사고팔겠다고 말하는 줄이다. 지금 스키마로는 전부 버려지는데, 장외 호가창
동역학(§11)에서는 **이게 곧 수요·공급의 바구니 단위**라서 버리면 안 된다.

## 축이 둘이다

딜러는 만기를 두 가지로 말한다.

    잔존만기   `1.5~3년` · `3년 이내` · `잔존 3~6개월` · `3년 내외`
    만기 연월   `24년 3~4월` · `24.9월~10월` · `2028~29년` · `25년 말~26년 초`

뒤쪽은 메시지 날짜를 빼면 잔존만기가 된다. 그래서 **둘 다 `TenorLo`/`TenorHi`
(년 단위) 하나로 모은다** — 하류가 축을 둘 볼 필요가 없다.

## 정밀도를 재현율보다 앞에 둔다

애매하면 NULL 로 둔다. 「25년 말」 같은 어림수는 분기로 편다(말=10~12월,
초=1~3월, 중=5~8월)고 규약을 못 박고, 그 규약이 안 통하는 표현은 안 잡는다.

## 왜 `RatingCat` 을 같이 넣었나 [내 판단 — 오너 확인 필요]

오너가 지시한 건 `TenorLo`·`TenorHi`·`SectorCat` 셋인데 `RatingCat` 을 더 넣었다.
호가창 바구니로 쓰려면 «3년 회사채» 는 등급 없이는 한 바구니가 아니기 때문이다
(A급과 AA급은 다른 시장이다). 필요 없으면 열 하나만 빼면 된다.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────── 섹터 범주
# 긴 낱말·구체적인 것을 먼저. '시은계 캐피탈' 은 여전채이지 은행채가 아니므로
# 여전채가 은행채보다 앞이어야 한다.
# ★'시은계 캐피탈' 은 여전채이지 은행채가 아니다. 「은행 이름 + 캐피탈/카드」는
#   한 낱말이므로 범주를 세기 전에 앞머리를 지워 둘로 안 세게 한다.
RE_BANK_AFFIL = re.compile(r'(?:시은|특은|은행|국은)\s*계?\s*(?=캐피탈|카드)')

SECTOR_CAT = [
    ("MBS",      re.compile(r'MBS|주택저당|주금공')),
    ("전단채",    re.compile(r'전단채|기업어음|(?<![A-Za-z])CP(?![A-Za-z])|ABSTB')),
    ("CD",       re.compile(r'(?<![A-Za-z])CD(?![A-Za-z])|씨디')),
    ("여전채",    re.compile(r'여전채|여전|캐피탈|카드채|(?<![가-힣])카드(?![가-힣])'
                            r'|할부금융|리스')),
    ("증권채",    re.compile(r'증권채')),
    # ★'사채' 만 쓰면 «공사채» 안의 사채가 걸린다(단위 검정에서 잡혔다).
    ("회사채",    re.compile(r'회사채|(?<![가-힣])사채(?![가-힣])')),
    # 국은 = 은행인 것은 확실하다(국은 CD·국은채 민평). 어느 은행인지는 미확정 —
    # 섹터 판정에는 «은행» 이면 충분하므로 여기 두고, 정체는 오너 목록으로 물었다.
    ("은행채",    re.compile(r'은행채|시은|특은|중금채|산금|기은|수은|국은'
                            r'|(?<![가-힣])은행(?![가-힣])')),
    ("공사채",    re.compile(r'공사채|(?<![가-힣])공사(?![가-힣])|공단')),
    ("지방/첨가", re.compile(r'도철|서철|지방채|토지주택|토주|예특|지역개발')),
    ("국고",      re.compile(r'(?<![가-힣])국고(?![가-힣])|국채')),
    ("통안",      re.compile(r'통안')),
    ("크레딧",    re.compile(r'크레딧')),
]

# ─────────────────────────────────────────────── 등급
RE_RATING = re.compile(
    r'(?<![A-Za-z])(AAA|AA\+|AA0|AA-|A\+|A0|A-|BBB\+|BBB0|BBB-|BBB)(?![A-Za-z])'
    r'|(?<![가-힣])(A급|싱글에이|더블에이|트리플에이)(?![가-힣])')
RE_RATING_BOUND = re.compile(r'(이상|이하|이내)')

# ─────────────────────────────────────────────── 잔존만기
_N = r'(\d+(?:\.\d+)?)'
RE_T_RANGE_Y = re.compile(_N + r'\s*[~∼–—-]\s*' + _N + r'\s*년')
RE_T_RANGE_M = re.compile(r'(\d+)\s*[~∼–—-]\s*(\d+)\s*개?\s*월')
RE_T_UNDER   = re.compile(_N + r'\s*년\s*(?:이내|이하|미만|안|짜리\s*이내)')
RE_T_OVER    = re.compile(_N + r'\s*년\s*이상')
RE_T_ABOUT   = re.compile(r'(?:잔존\s*)?' + _N + r'\s*년\s*(?:내외|정도|짜리|물|물건)?')
RE_T_MONTH   = re.compile(r'(\d+)\s*개월')

# ─────────────────────────────────────────────── 만기 연월
RE_M_YMM = re.compile(r'(\d{2})\s*[년.]\s*(\d{1,2})\s*월?\s*[~∼–—-]\s*(\d{1,2})\s*월')
RE_M_YM  = re.compile(r'(\d{2})\s*[년.]\s*(\d{1,2})\s*월')
RE_M_YY  = re.compile(r'(20\d{2})\s*[~∼–—-]\s*(\d{2,4})\s*년')
RE_M_YQ  = re.compile(r'(\d{2})\s*년\s*(초|중|말)')
# 「25년 말~ 26년 초」 처럼 두 어림수를 잇는 꼴
RE_M_YQ2 = re.compile(r'(\d{2})\s*년\s*(초|중|말)\s*[~∼–—-]\s*(\d{2})\s*년\s*(초|중|말)')

QUARTER = {"초": (1, 3), "중": (5, 8), "말": (10, 12)}


def _ym(yy: int, mm: int) -> float:
    """2자리 연도 + 월 -> 연 단위 소수 (2024.25 꼴)."""
    return 2000 + yy + (mm - 1) / 12.0


def _tenor_from_maturity(text: str, date_year: float):
    """만기 연월 표현 -> (잔존 lo, hi). 못 읽으면 (nan, nan)."""
    m = RE_M_YQ2.search(text)
    if m:
        y1, q1, y2, q2 = int(m.group(1)), m.group(2), int(m.group(3)), m.group(4)
        lo = _ym(y1, QUARTER[q1][0])
        hi = _ym(y2, QUARTER[q2][1])
        return lo - date_year, hi - date_year
    m = RE_M_YMM.search(text)
    if m:
        yy, m1, m2 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= m1 <= 12 and 1 <= m2 <= 12:
            # '25.12월~1월' 처럼 해가 넘어가면 뒤쪽은 다음 해다
            y2 = yy + (1 if m2 < m1 else 0)
            return _ym(yy, m1) - date_year, _ym(y2, m2) - date_year
    m = RE_M_YY.search(text)
    if m:
        y1 = int(m.group(1))
        g2 = m.group(2)
        y2 = int(g2) if len(g2) == 4 else 2000 + int(g2)
        return y1 - date_year, (y2 + 1) - date_year
    m = RE_M_YQ.search(text)
    if m:
        yy, q = int(m.group(1)), m.group(2)
        return _ym(yy, QUARTER[q][0]) - date_year, _ym(yy, QUARTER[q][1]) - date_year
    m = RE_M_YM.search(text)
    if m:
        yy, mm = int(m.group(1)), int(m.group(2))
        if 1 <= mm <= 12:
            return _ym(yy, mm) - date_year, _ym(yy, mm) - date_year
    return np.nan, np.nan


def _tenor_direct(text: str):
    """잔존만기 표현 -> (lo, hi). 못 읽으면 (nan, nan)."""
    m = RE_T_RANGE_Y.search(text)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        if a <= b <= 60:
            return a, b
    m = RE_T_RANGE_M.search(text)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a <= b <= 120:
            return a / 12.0, b / 12.0
    m = RE_T_UNDER.search(text)
    if m:
        return 0.0, float(m.group(1))
    m = RE_T_OVER.search(text)
    if m:
        return float(m.group(1)), np.nan
    m = RE_T_MONTH.search(text)
    if m:
        v = int(m.group(1)) / 12.0
        return v, v
    m = RE_T_ABOUT.search(text)
    if m:
        v = float(m.group(1))
        if v <= 60:
            return v, v
    return np.nan, np.nan


def extract(text: str, date_year: float):
    """한 줄 -> (TenorLo, TenorHi, SectorCat, RatingCat).

    date_year 는 메시지 날짜의 연 단위 소수(2024.62 꼴). 만기 연월을 잔존으로
    바꿀 때만 쓴다. 없으면 nan 을 주면 그 축은 건너뛴다.
    """
    t = str(text)

    # 만기 연월이 먼저다 — '24년 3~4월' 을 잔존 '3~4년' 으로 읽으면 안 된다.
    lo, hi = (np.nan, np.nan)
    if not np.isnan(date_year):
        lo, hi = _tenor_from_maturity(t, date_year)
    if np.isnan(lo):
        lo, hi = _tenor_direct(t)
    # 과거·비현실 값은 버린다(잔존이 음수이거나 60년 초과)
    if not np.isnan(lo) and (lo < -0.5 or lo > 60):
        lo, hi = np.nan, np.nan
    if not np.isnan(hi) and (hi < -0.5 or hi > 60):
        hi = np.nan
    if not np.isnan(lo):
        lo = max(lo, 0.0)

    cat_text = RE_BANK_AFFIL.sub("", t)     # 은행계 캐피탈을 둘로 안 센다
    cats = [name for name, rx in SECTOR_CAT if rx.search(cat_text)]
    sector = "|".join(cats) if cats else None

    rs = []
    for m in RE_RATING.finditer(t):
        rs.append(m.group(1) or m.group(2))
    rating = None
    if rs:
        rating = "|".join(dict.fromkeys(rs))
        b = RE_RATING_BOUND.search(t[max(0, t.find(rs[-1])):])
        if b:
            rating += f"({b.group(1)})"

    return (float(lo) if not np.isnan(lo) else None,
            float(hi) if not np.isnan(hi) else None,
            sector, rating)


def apply_frame(msg: pd.Series, date: pd.Series) -> pd.DataFrame:
    """열 넷을 한꺼번에 만든다."""
    d = pd.to_datetime(date, errors="coerce")
    dy = d.dt.year + (d.dt.dayofyear - 1) / 365.25
    out = [extract(m, y if pd.notna(y) else np.nan)
           for m, y in zip(msg.astype(str), dy)]
    return pd.DataFrame(out, index=msg.index,
                        columns=["TenorLo", "TenorHi", "SectorCat", "RatingCat"])


# ───────────────────────────────────────────── 단위 검정
TESTS = [
    ("A급 회사채  1.5~3년 정도 매수 관심", 2024.5, (1.5, 3.0, "회사채", "A급")),
    ("2~3년 은행 공사 사자", 2024.5, (2.0, 3.0, "은행채|공사채", None)),
    ("3년 이내 A급 회사채 사자", 2024.5, (0.0, 3.0, "회사채", "A급")),
    ("1년 이내 CD사자", 2024.5, (0.0, 1.0, "CD", None)),
    ("3개월 공사 특은 사자", 2024.5, (0.25, 0.25, "은행채|공사채", None)),
    ("잔존 3년 A급 회사채 매수관심", 2024.5, (3.0, 3.0, "회사채", "A급")),
    ("3년 내외 시은캐피탈  사자", 2024.5, (3.0, 3.0, "여전채", None)),
    ("2~5년 AA-이상 회사채 사자", 2024.5, (2.0, 5.0, "회사채", "AA-(이상)")),
    # 만기 연월 축 — 잔존으로 바뀌어야 한다
    ("24년 3~4월 시은채 사자", 2024.0, (2 / 12, 3 / 12, "은행채", None)),
    ("24.9월~10월 국은채 사자", 2024.0, (8 / 12, 9 / 12, "은행채", None)),
    ("2028~29년 공사채 사자", 2024.0, (4.0, 6.0, "공사채", None)),
    ("25년 말~ 26년 초 여전채/ 크레딧 사자  +12빕", 2024.0,
     (2025 + 9 / 12 - 2024, 2026 + 2 / 12 - 2024, "여전채|크레딧", None)),
    # 잡히면 안 되는 것
    ("24-8 66- 팔자", 2024.5, (None, None, None, None)),
    ("26.2.2 JB우리캐피탈 502-5(AA-)팔자", 2026.1, None),   # 만기일 있는 행이라 호출 안 됨
]


def selftest() -> int:
    bad = 0
    for text, dy, exp in TESTS:
        if exp is None:
            continue
        got = extract(text, dy)
        ok = True
        for g, e in zip(got, exp):
            if e is None:
                ok &= g is None
            elif isinstance(e, float):
                ok &= g is not None and abs(g - e) < 0.02
            else:
                ok &= g == e
        if not ok:
            bad += 1
            print(f"  FAIL  {text[:44]!r}\n        기대 {exp}\n        실제 {got}")
        else:
            print(f"  OK    {text[:44]!r}")
    n = len([t for t in TESTS if t[2] is not None])
    print(f"\n단위 검정 {n - bad}/{n}")
    return bad


if __name__ == "__main__":
    raise SystemExit(1 if selftest() else 0)
