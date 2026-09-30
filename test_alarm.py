# -*- coding: utf-8 -*-
"""「방금 온 싼 오퍼」 알람 판정 단위시험. [설계 `PROMPT_next_2026-09-30-alarm.md`]

    python -m pytest test_alarm.py -q

서버를 띄우지 않는다 — `kbond_view.alarm_hits` 는 순수 함수다(상태 없음).

왜 이 파일이 있는가: [OWNER] 의 첫 말은 「1등이 바뀌면 알람」이었는데 **재 보고 방아쇠를
바꿨다** — 1등 교체의 43%가 「직전 1등이 TTL 로 죽어 더 나쁜 것이 왕관을 물려받은」
것이었다(수는 `archive/docs/RESULT_alarm_sizing_2026-09-30.md` §2). 여기서 재는 것은
그 판정이 **문턱과 나이와 모집단을 규약대로 보는가**다.
"""
from __future__ import annotations

import kbond_view as KV

T = 50_000          # 기준 시각(자정 이후 초)


def _bucket(cls="은행채", rt="AAA", lo=0.0, hi=1.0, n=8, bp_med=0.0,
            bpc_med=0.0, est=False):
    return {"cls": cls, "rt": rt, "ttm_lo": lo, "ttm_hi": hi, "n": n,
            "bp_med": bp_med, "bpc_med": bpc_med, "est": est}


def _offer(**over):
    o = {"s": "S", "atmp": False, "lvl": None, "t": T - 10, "cls": "은행채",
         "rt": "AAA", "ttm": 0.5, "bpe": 5.0, "bpc": 5.0, "n": "KB국민은행1-1",
         "d": "H01", "a": 100.0, "pk": "은행채 AAA ~1년", "pr": 1, "pn": 8}
    o.update(over)
    return o


def _hits(offers, buckets=None, **kw):
    return KV.alarm_hits(offers, buckets or [_bucket()], T, **kw)


# ── 울리는 자리 ─────────────────────────────────────────────────────────────
def test_무리_중앙보다_문턱만큼_싸면_울린다():
    h = _hits([_offer(bpc=5.0)], [_bucket(bpc_med=0.0)], n_bp=3.0)
    assert len(h) == 1
    assert h[0]["dev"] == 5.0 and h[0]["adj"] is True
    assert h[0]["key"] == f"H01|KB국민은행1-1|{T-10}"


def test_문턱_미만이면_안_울린다():
    assert _hits([_offer(bpc=2.9)], [_bucket(bpc_med=0.0)], n_bp=3.0) == []


def test_문턱_정확히_같으면_울린다():
    """`>=` 다 — 경계를 비워 두면 그 칸에서 판정이 흔들린다."""
    assert len(_hits([_offer(bpc=3.0)], [_bucket(bpc_med=0.0)], n_bp=3.0)) == 1


def test_싼_것부터_줄_세운다():
    a = _offer(bpc=4.0, n="A", d="H01")
    b = _offer(bpc=9.0, n="B", d="H02")
    h = _hits([a, b], [_bucket(bpc_med=0.0)], n_bp=3.0)
    assert [x["n"] for x in h] == ["B", "A"]


# ── 나이 = 1분 벼랑 ─────────────────────────────────────────────────────────
def test_나이_창_안이면_울리고_넘으면_안_울린다():
    """★창은 60초다 — 최우선 나이별 그 레벨 체결률이 ~1분 90.6% → 1~5분 61.2% 로
    꺾인다(국고 전 이력 35,654건). 1분 넘은 것을 알리면 이미 값이 반이다."""
    assert len(_hits([_offer(t=T - 60, bpc=5.0)], [_bucket(bpc_med=0.0)])) == 1
    assert _hits([_offer(t=T - 61, bpc=5.0)], [_bucket(bpc_med=0.0)]) == []


def test_미래_시각은_안_울린다():
    """되감기·시계 어긋남에서 음수 나이가 나올 수 있다 — 그때 울리면 안 된다."""
    assert _hits([_offer(t=T + 5, bpc=5.0)], [_bucket(bpc_med=0.0)]) == []


# ── 침묵해야 하는 자리 ───────────────────────────────────────────────────────
def test_비드는_안_울린다():
    assert _hits([_offer(s="B", bpc=5.0)], [_bucket(bpc_med=0.0)]) == []


def test_민평에는_안_울린다():
    """부른 값이 없다 — 책의 3분의 2가 여기 있다(실측 67%)."""
    assert _hits([_offer(atmp=True, bpc=5.0)], [_bucket(bpc_med=0.0)]) == []


def test_레벨이_가정이면_안_울린다():
    assert _hits([_offer(lvl="est", bpc=5.0)], [_bucket(bpc_med=0.0)]) == []


def test_무리가_작으면_안_울린다():
    """`PEER_MIN` 미만에서는 중앙값이 뜻이 없다."""
    small = _bucket(n=KV.PEER_MIN - 1, bpc_med=0.0)
    assert _hits([_offer(bpc=5.0)], [small]) == []


def test_중앙값이_없으면_안_울린다():
    """뺄 수 없으면 «—» 라는 이 레인 규율 — 0 으로 가정하지 않는다."""
    assert _hits([_offer(bpc=5.0, bpe=None)], [_bucket(bpc_med=None, bp_med=None)]) == []


def test_무리가_없으면_안_울린다():
    far = _bucket(lo=5.0, hi=10.0, bpc_med=0.0)
    assert _hits([_offer(ttm=0.5, bpc=5.0)], [far]) == []


# ── ★재는 자가 하나 ─────────────────────────────────────────────────────────
def test_무리가_커브반영을_못_가지면_민평대비로_잰다():
    """섞어서 재지 않는다 — `peer_rank` 와 같은 규칙."""
    b = _bucket(bpc_med=None, bp_med=1.0)
    h = _hits([_offer(bpe=6.0, bpc=5.0)], [b], n_bp=3.0)
    assert len(h) == 1
    assert h[0]["adj"] is False
    assert h[0]["val"] == 6.0 and h[0]["med"] == 1.0 and h[0]["dev"] == 5.0


def test_커브반영이_있으면_그것으로_잰다():
    b = _bucket(bpc_med=1.0, bp_med=0.0)
    h = _hits([_offer(bpe=9.0, bpc=5.0)], [b], n_bp=3.0)
    assert h[0]["adj"] is True and h[0]["dev"] == 4.0   # 5.0 − 1.0, 민평대비가 아니다


# ── 부가 ───────────────────────────────────────────────────────────────────
def test_등급이_집계에서_온_무리는_그_사실을_싣는다():
    h = _hits([_offer(bpc=5.0)], [_bucket(bpc_med=0.0, est=True)], n_bp=3.0)
    assert h[0]["est"] is True


def test_열쇠는_같은_도착에_같다():
    """5초 폴이면 한 도착이 최대 12번 보인다 — 소비자가 이 열쇠로 접는다."""
    o = _offer(bpc=5.0)
    k1 = _hits([o], [_bucket(bpc_med=0.0)])[0]["key"]
    k2 = _hits([dict(o)], [_bucket(bpc_med=0.0)])[0]["key"]
    assert k1 == k2


def test_모집단을_거른_것을_넣으면_결과가_줄어든다():
    """⚠모집단은 `cr_ranked` 의 것(거르기 전)이어야 한다. 이 시험은 그 계약을
    말로만 두지 않는다 — 거른 목록을 넣으면 답이 달라지는 것을 박아 둔다."""
    a = _offer(bpc=5.0, n="A", d="H01")
    b = _offer(bpc=7.0, n="B", d="H02", rt="AA+")
    bks = [_bucket(bpc_med=0.0), _bucket(rt="AA+", bpc_med=0.0)]
    assert len(_hits([a, b], bks, n_bp=3.0)) == 2
    assert len(_hits([a], bks, n_bp=3.0)) == 1      # 「AAA 만」으로 걸러 넣으면 하나를 잃는다
