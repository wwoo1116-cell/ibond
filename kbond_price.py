# -*- coding: utf-8 -*-
"""수익률 <-> 단가(액면 10,000). 관행적 복할인. [2026-09-23]

왜 이 파일이 있는가 — 이 레인은 값을 늘 «금리» 로만 말해 왔다. 딜러는 «원» 으로도
말하고(크레딧 1년 내외), 트레이더는 화면의 금리를 보고 **따로 원 계산기를 돌린다.**
그 계산기를 화면 안으로 들여오는 것이 이 파일이다.

★규약은 내가 고른 것이 아니라 정답지에 맞춘 것이다 — NICE피앤아이 Bond Market
  Daily 2026-09-23 「통안/국고채 단가조정 금리표」의 32행(당일결제 18 + 익일결제 14).
  `test_price.py` 가 그 32행을 통째로 들고 있다. 식을 고치면 그게 먼저 운다.

    P = [ Σ_k CF_k / (1+r/m)^k ] / (1 + r/m × d/D)        앞은 복리, 마지막 토막은 단리
      r = 수익률/m · d = 결제일→다음 이표일 실일수 · D = 그 이표기간 실일수

★주기 m 은 테너가 아니라 «발행체 × 이자종류» 가 정한다:
    국고·외평 이표채 m=2(06M) · 통안 이표채 m=4(03M) · 할인채는 단리 365.
  처음에 통안을 반기로 놓고 72원 틀렸다. 국고 감각을 통안에 옮기지 마라.

★「1원 ≈ 1bp」는 거짓이다. 1원이 몇 bp 인지는 듀레이션이 정한다 — 30년물 0.06bp,
  4.5년물 0.24bp, 2.7년물 0.38bp. 어림으로 환산하면 장기물에서 자릿수가 틀린다.
  그래서 `bp_per_won()` 은 표를 보간하지 않고 **그 종목을 두 번 값매겨** 잰다.

밖에 있는 것 — 물가연동국채(원금이 물가에 연동) · STRIPS · 크레딧(마스터 없음).
  셋 다 `spec_of()` 가 None 을 주고, 하류는 지어내지 말고 비운다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache

from dateutil.relativedelta import relativedelta

FACE = 10_000.0


# ─────────────────────────────────────────────────────────────── 제원
@dataclass(frozen=True)
class Spec:
    """종목 하나의 제원. 이것만 있으면 금리를 값으로 바꿀 수 있다."""
    key: str                 # 종목명('26-3') 또는 표준코드
    name: str
    maturity: date
    coupon: float            # 표면이율 %, 할인채면 0
    m: int                   # 연 지급횟수. 할인채면 0
    kind: str                # '이표채' | '할인채'

    @property
    def is_discount(self) -> bool:
        return self.kind == "할인채" or self.m == 0


# ─────────────────────────────────────────────────────────── 값매김
def coupon_dates(maturity: date, settle: date, m: int) -> tuple[list[date], date]:
    """결제일 이후의 이표일들(오름차순)과 «직전» 이표일.

    ★만기일에서 역산한다. 발행일에서 앞으로 세면 마지막 토막이 어긋난다.
    """
    out, d = [], maturity
    while d > settle:
        out.append(d)
        d -= relativedelta(months=12 // m)
    return sorted(out), d


def price_coupon(coupon: float, maturity: date, ytm: float,
                 settle: date, m: int, face: float = FACE) -> float:
    """이표채 단가. 앞은 복리, 마지막 토막은 단리(관행적 복할인)."""
    cfs, prev = coupon_dates(maturity, settle, m)
    c = face * coupon / 100.0 / m
    r = ytm / 100.0 / m
    D = (cfs[0] - prev).days
    d = (cfs[0] - settle).days
    acc = sum((c + (face if cf == maturity else 0.0)) / (1 + r) ** k
              for k, cf in enumerate(cfs))
    return acc / (1 + r * d / D)


def price_discount(ytm: float, maturity: date, settle: date,
                   face: float = FACE) -> float:
    """할인채(통안 DC 등). 단리 365."""
    return face / (1 + ytm / 100.0 * (maturity - settle).days / 365.0)


def price(spec: Spec, ytm: float, settle: date) -> float | None:
    """수익률(%) -> 단가. 만기가 지났으면 None(지어내지 않는다)."""
    if spec.maturity <= settle:
        return None
    if spec.is_discount:
        return price_discount(ytm, spec.maturity, settle)
    return price_coupon(spec.coupon, spec.maturity, ytm, settle, spec.m)


def bp_per_won(spec: Spec, ytm: float, settle: date) -> float | None:
    """이 종목에서 «1원» 이 몇 bp 인가.

    ★표를 보간하지 않고 그 종목을 +1bp 로 한 번 더 값매겨 잰다 — 듀레이션 근사가
      아니라 같은 식을 두 번 쓰는 것이라 잔존이 짧아도 안 깨진다.
    """
    p0 = price(spec, ytm, settle)
    p1 = price(spec, ytm + 0.01, settle)
    if p0 is None or p1 is None or p0 == p1:
        return None
    return 1.0 / abs(p0 - p1)


def won_of(spec: Spec, ytm: float, ref_ytm: float, settle: date) -> float | None:
    """★수정가액 — 기준(전일 민평) 대비 «원».

    부호 규약은 레인 전체와 같다: **+원 = 단가 비쌈 = 금리 낮음**.
    """
    p, p0 = price(spec, ytm, settle), price(spec, ref_ytm, settle)
    return None if (p is None or p0 is None) else p - p0


# ───────────────────────────────────────────────────── 마스터(DB)
def _engine():
    from sqlalchemy import create_engine
    need = ["BW_MYSQL_USER", "BW_MYSQL_PASSWORD", "BW_MYSQL_HOST", "BW_MYSQL_PORT"]
    miss = [k for k in need if not os.environ.get(k)]
    if miss:
        raise RuntimeError(f"환경변수 없음: {', '.join(miss)}")
    return create_engine(
        f"mysql+pymysql://{os.environ['BW_MYSQL_USER']}:{os.environ['BW_MYSQL_PASSWORD']}"
        f"@{os.environ['BW_MYSQL_HOST']}:{os.environ['BW_MYSQL_PORT']}/infomax?charset=utf8mb4",
        pool_pre_ping=True)


_TERM = {"03M": 4, "06M": 2, "12M": 1}


def _as_date(v) -> date:
    return v.date() if isinstance(v, datetime) else v


@lru_cache(maxsize=1)
def load_specs() -> dict[str, Spec]:
    """국고·외평(종목명 'YY-N') + 통안(표준코드) 제원표.

    ⚠`국채_발행정보` 489행 중 **322행이 STRIPS** 다. `이자종류='이표채'` 로 거르지
      않으면 분리채가 섞인다. 물가연동국채도 여기서 뺀다 — 원금이 물가에 연동돼
      이 식으로는 틀린 값이 «조용히» 나온다.
    """
    import pandas as pd
    from sqlalchemy import text

    out: dict[str, Spec] = {}
    with _engine().connect() as c:
        g = pd.read_sql(text(
            "SELECT 표준코드, 종목명, 만기일, 표면이율, 이자종류, 이자지급기간 "
            "FROM `국채_발행정보` "
            "WHERE 이자종류 = '이표채' AND 인포맥스소분류 <> '물가연동국채'"), c)
        t = pd.read_sql(text(
            "SELECT 표준코드, 종목명, 만기일, 표면이율, 이자종류, 이자지급기간 "
            "FROM `통안채_발행정보`"), c)

    for df, keycol in ((g, "종목명"), (t, "표준코드")):
        for _, r in df.iterrows():
            m = _TERM.get(str(r["이자지급기간"]).strip())
            if m is None:
                continue
            sp = Spec(key=str(r[keycol]), name=str(r["종목명"]),
                      maturity=_as_date(r["만기일"]), coupon=float(r["표면이율"]),
                      m=m, kind=str(r["이자종류"]).strip())
            out[sp.key] = sp
            if keycol == "종목명":
                out[str(r["표준코드"])] = sp      # 두 키 다 받는다
    return out


def spec_of(key: str | None) -> Spec | None:
    """종목명('26-3')이나 표준코드로 제원을 찾는다. 없으면 None — 지어내지 않는다."""
    if not key:
        return None
    try:
        return load_specs().get(str(key).strip())
    except Exception:
        return None                              # DB 가 없어도 화면은 서야 한다


# ──────────────────────────────────────────────── 검산 (O / X)
#  [OWNER 2026-09-23] 「단가 = 수정가액 = 실제 금리가 정합한지 확인하는거야.
#   그래야 트레이더가 이를 보고 신뢰해서 따로 원 계산기 안 돌려도 되는거니까」
#
#  ★두 길을 따로 걸어 만나는지 본다 — 한 길로만 가면 검산이 아니라 항등식이다.
#    길 A  현금흐름으로 «값매겨» 낸 원          price(y) − price(민평)
#    길 B  데스크가 실제로 쓰는 어림으로 «환산한» 원  `enrich_kbond_quotes.won_to_bp`
#  길 B 가 곧 트레이더의 원 계산기다. O 는 «그 계산기를 안 돌려도 된다» 는 뜻이고,
#  X 는 «이 종목에선 그 어림이 안 맞는다» 는 뜻이다.
#
#  ★★★길 B 는 잔존 0.125~2.50년 실측표이고 그 밖은 `1/TTM` 으로 잇는다. 그 외삽이
#    장기물에서 깨진다 — 2026-09-23 실측: 1.7년 0.94배 · 4.5년 0.90배 · 9.2년 0.78배 ·
#    **29.5년 0.50배**. 그래서 표 밖에서는 길 B 를 «그 종목의 참 bp/원» 으로 바꿔
#    건다. 09-22 §7 의 「원↔bp 맞는다」 판정은 잔존 2.5년 아래 크레딧 모집단의
#    것이라 그대로 서지만, 국고 장기물로는 넘어가지 않는다.
TOL_WON = 0.10          # 두 길의 차 허용치(원). NICE 표시 반올림 0.01 의 열 배.
TBL_MAX_TTM = 2.50      # `won_to_bp` 실측표(TTM_GRID)의 오른쪽 끝


def _won_desk(ytm: float, ref_ytm: float, ttm: float,
              spec: Spec, settle: date) -> float | None:
    """길 B — 데스크 어림으로 «원». 표 밖이면 그 종목의 참 bp/원으로 건다."""
    if ttm <= TBL_MAX_TTM:
        try:
            from enrich_kbond_quotes import won_to_bp
        except Exception:
            return None
        # won_to_bp(원, 잔존) -> bp. 1원이 몇 bp 인지 그 표에 물어본다.
        r = abs(float(won_to_bp(1.0, ttm)))
    else:
        r = bp_per_won(spec, ref_ytm, settle) or 0.0
    return None if not r else -(ytm - ref_ytm) * 100.0 / r   # +원 = 금리 낮음


def crosscheck(spec: Spec | None, ytm: float | None, ref_ytm: float | None,
               settle: date, tol: float = TOL_WON) -> tuple[str, dict]:
    """('O'|'X'|'', 근거). 잴 수 없으면 ''(빈칸) — 모르는 것을 O 로 적지 않는다."""
    if spec is None or ytm is None or ref_ytm is None:
        return "", {}
    won_cf = won_of(spec, ytm, ref_ytm, settle)               # 길 A
    if won_cf is None:
        return "", {}
    ttm = (spec.maturity - settle).days / 365.0
    won_desk = _won_desk(ytm, ref_ytm, ttm, spec, settle)     # 길 B
    if won_desk is None:
        return "", {}
    gap = abs(won_cf - won_desk)
    return ("O" if gap <= tol else "X"), {
        "won": round(won_cf, 2), "won_desk": round(won_desk, 2),
        "gap": round(gap, 3), "ttm": round(ttm, 2),
        "src": "표" if ttm <= TBL_MAX_TTM else "값매김"}
