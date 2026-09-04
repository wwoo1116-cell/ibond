# -*- coding: utf-8 -*-
"""끝전 절사 보정 환산 단위시험. [PROMPT_frac_2026-09-03.md [4]a]

서버를 띄우지 않는다 — 순수 함수만 본다.
    python -m pytest test_frac.py -q

왜 이 파일이 있는가: `kbond_test.py` 는 GUI 자동화라 단위시험 자리가 아니다.
그리고 이 레인에서 두 번 데인 것이 «넓힌 정규식이 기존 값을 흔든다» 였다(T14).
정규식을 새로 쓰지 않고 enrich 의 것을 임포트하는 규약을 여기서 못 박는다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import kbond_live as KL                                          # noqa: E402


# ── 1. 끝전 추출 10건 ────────────────────────────────────────────────
#   ★'끝전0.4' 가 0.0 이 되는 사고가 본표 53,595행에 있었다(한 갈래 정규식이
#     선행 0 을 먹었다). 범위검사를 통과하는 틀린 값이라 더 위험했다.
@pytest.mark.parametrize("body, want, src", [
    ("28.1.1 A사 끝전0.4 +1원 팔자", 0.4, "stated"),
    ("28.1.1 A사 (민3.5 끝.45) 팔자", 0.45, "stated"),
    ("28.1.1 A사 끝전 .5 팔자", 0.5, "stated"),
    ("28.1.1 A사 끝54 팔자", 0.54, "stated"),
    ("28.1.1 A사 끝전 9 팔자", 0.9, "stated"),
    ("28.1.1 A사 (민3.574 끝9원) 팔자", 0.9, "stated"),
    ("28.1.1 A사 (민 2.883%, 0.76원) 팔자", 0.76, "list"),
    ("28.1.1 A사 민 3.578 팔자", None, None),
    ("28.1.1 A사 끝전 1.2 팔자", None, None),          # [0,1) 밖은 결측
    ("28.1.1 A사 끝100 팔자", None, None),             # 〃
])
def test_mp_frac(body, want, src):
    got, gsrc = KL.mp_frac(body)
    assert got == want and gsrc == src


# ── 2. 환산 항등식 4건 (실제 메시지 · PROMPT_frac §A) ────────────────
#   예측 = 문면민평 + won_to_bp(원 − 끝전, 잔존)/100 이 딜러가 적어 준
#   결과금리와 0.3bp 안에서 맞아야 한다.
@pytest.mark.parametrize("body, mp, ttm, quoted", [
    ("24.9.21 중금채 민3.648(끝.11원).. +1원팔자 3.632%", 3.648, 0.59, 3.632),
    ("26.8.28 하나은행 (민2.843% / 끝전 .02) +1원 팔자 2.836%", 2.843, 1.46, 2.836),
    ("26.9.9(수)서부발전(민2.522%/끝.92원/쿠폰1.609%)[10억]+1원팔자 2.521%",
     2.522, 1.17, 2.521),
    ("27.1.9(토)산금(민2.713%/끝.86원)+1원팔자 2.711%", 2.713, 1.00, 2.711),
])
def test_conversion_identity(body, mp, ttm, quoted):
    frac, _ = KL.mp_frac(body)
    assert frac is not None
    pred = mp + KL.frac_bp(1.0, frac, ttm) / 100
    assert abs(pred - quoted) * 100 <= 0.3, f"{pred} vs {quoted}"


def test_frac_matters():
    """끝전을 무시하면 같은 «+1원» 이 열 배 갈린다 — 이 레인의 존재 이유."""
    near_par = KL.frac_bp(1.0, 0.92, 1.17)       # 실제 0.08원어치
    near_full = KL.frac_bp(1.0, 0.11, 0.59)      # 실제 0.89원어치
    assert abs(near_par) < 0.2
    assert abs(near_full) > 1.0
    assert abs(KL.frac_bp(1.0, 0.0, 1.17)) > abs(near_par) * 5


# ── 3. 단 배정 6건 (Q · C · E · N + 경계 둘) ─────────────────────────
def assign(abs_yield, mp, ttm, frac):
    """_feed_one 크레딧 원 갈래의 판정만 떼어낸 것 — 같은 순서로 본다."""
    ok = (mp is not None and ttm is not None and ttm > 0)
    if abs_yield is not None:
        return "quoted"
    if ok and frac is not None:
        return "conv"
    if ok and ttm >= KL.FRAC_EST_MIN_TTM:
        return "est"
    return None


@pytest.mark.parametrize("aby, mp, ttm, frac, want", [
    (3.9, 3.8, 1.0, 0.4, "quoted"),      # Q: 결과금리가 있으면 그것이 진실
    (None, 3.8, 1.0, 0.4, "conv"),       # C: 끝전으로 정확 환산
    (None, 3.8, 1.0, None, "est"),       # E: 끝전 없음 + 잔존 충분
    (None, None, 1.0, 0.4, None),        # N: 민평 없음
    (None, 3.8, 0.75, None, "est"),      # 경계: 0.75 딱 = E
    (None, 3.8, 0.74, None, None),       # 경계: 0.74 = N (지어내지 않는다)
])
def test_level_assignment(aby, mp, ttm, frac, want):
    assert assign(aby, mp, ttm, frac) == want


def test_zero_or_negative_ttm_is_unknown():
    """만기가 지났거나 오늘인 행은 환산하지 않는다(1/ttm 이 폭발한다)."""
    assert assign(None, 3.8, 0.0, 0.4) is None
    assert assign(None, 3.8, -1.0, 0.4) is None


# ── 4. 부호 규약 ─────────────────────────────────────────────────────
def test_sign_convention():
    """+원 = 단가 비쌈 = 금리 낮음. 이 부호를 뒤집으면 책 전체가 뒤집힌다."""
    assert KL.frac_bp(1.0, 0.0, 1.0) < 0        # +1원이면 민평보다 금리가 낮다
    assert KL.frac_bp(-1.0, 0.0, 1.0) > 0
    assert KL.frac_bp(0.5, 0.5, 1.0) == 0       # 원 == 끝전이면 민평 그 자체


def test_out_of_grid_uses_inverse_ttm():
    """실측표(0.125~2.5년) 밖은 1/잔존 으로 잇는다."""
    assert KL.frac_bp(1.0, 0.0, 10.0) == pytest.approx(-0.1, abs=0.02)
    assert np.isfinite(KL.frac_bp(1.0, 0.0, 0.05))
