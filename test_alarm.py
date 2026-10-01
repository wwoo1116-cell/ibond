# -*- coding: utf-8 -*-
"""「방금 온 싼 오퍼」 알람 판정 단위시험. [설계 `PROMPT_next_2026-09-30-alarm.md`]

    python -m pytest test_alarm.py -q

서버를 띄우지 않는다 — `kbond_view.alarm_hits` 는 순수 함수다(상태 없음).

왜 이 파일이 있는가: [OWNER] 의 첫 말은 「1등이 바뀌면 알람」이었는데 **재 보고 방아쇠를
바꿨다** — 1등 교체의 43%가 「직전 1등이 TTL 로 죽어 더 나쁜 것이 왕관을 물려받은」
것이었다(수는 `archive/docs/RESULT_alarm_sizing_2026-09-30.md` §2). 여기서 재는 것은
그 판정이 **문턱과 나이와 모집단을 규약대로 보는가**다.

★★[2026-10-01] 무리를 **손으로 만들지 않는다.** 알람의 무리는 이제 `peer_rank` 의 것
하나(계열×등급×**잔존칸**)이고, 그래서 시험도 **실제 파이프라인을 태운다**(`_hits`).
그러면 이 시험들이 「알람이 화면 배지와 같은 무리를 보는가」까지 같이 지킨다.
그 전에는 `cr_buckets`(계열×등급 · 잔존 **통째**)를 무리로 썼는데, 시험이 버킷을 손으로
만들어 넣었기 때문에 **그 사실이 시험에 안 드러났다** — 17개가 전부 초록이었다.
"""
from __future__ import annotations

import kbond_view as KV

T = 50_000          # 기준 시각(자정 이후 초)


def _offer(**over):
    o = {"s": "S", "atmp": False, "lvl": None, "t": T - 10, "cls": "은행채",
         "rt": "AAA", "ttm": 0.5, "bpe": 5.0, "bpc": 5.0, "n": "KB국민은행1-1",
         "d": "H01", "a": 100.0, "rt_src": "문면"}
    o.update(over)
    return o


def _peers(n=5, bpe=0.0, bpc=0.0, **over):
    """무리를 채우는 «평범한» 또래. 중앙값을 이 값들이 정한다.

    ★나이는 창(60초) **밖**이고 TTL(30분) **안**이다 — 또래는 무리를 세우되 스스로는
      울리지 않아야 한다. 그래서 「울린 수」가 곧 주인공 수다.
    """
    return [_offer(n=f"또래{i}", d=f"P{i:02d}", bpe=bpe, bpc=bpc, t=T - 600, **over)
            for i in range(n)]


def _hits(offers, **kw):
    """`cr_ranked` 가 하는 일(또래 순위·중앙값 얹기)을 **같은 함수로** 태운 뒤 알람을 뽑는다."""
    rows = [dict(o) for o in offers]
    ranks = KV.peer_rank(rows)
    for e in rows:
        e.update(ranks.get(id(e)) or {})
    return KV.alarm_hits(rows, T, **kw)


# ── 울리는 자리 ─────────────────────────────────────────────────────────────
def test_무리_중앙보다_문턱만큼_싸면_울린다():
    h = _hits([_offer(bpc=5.0)] + _peers(), n_bp=3.0)
    assert len(h) == 1
    assert h[0]["dev"] == 5.0 and h[0]["adj"] is True
    assert h[0]["key"] == f"H01|KB국민은행1-1|{T-10}"


def test_문턱_미만이면_안_울린다():
    assert _hits([_offer(bpc=2.9)] + _peers(), n_bp=3.0) == []


def test_문턱_정확히_같으면_울린다():
    """`>=` 다 — 경계를 비워 두면 그 칸에서 판정이 흔들린다."""
    assert len(_hits([_offer(bpc=3.0)] + _peers(), n_bp=3.0)) == 1


def test_싼_것부터_줄_세운다():
    a = _offer(bpc=4.0, n="A", d="H01")
    b = _offer(bpc=9.0, n="B", d="H02")
    h = _hits([a, b] + _peers(), n_bp=3.0)
    assert [x["n"] for x in h] == ["B", "A"]


# ── 나이 = 1분 벼랑 ─────────────────────────────────────────────────────────
def test_나이_창_안이면_울리고_넘으면_안_울린다():
    """★창은 60초다 — 최우선 나이별 그 레벨 체결률이 ~1분 90.6% → 1~5분 61.2% 로
    꺾인다(국고 전 이력 35,654건). 1분 넘은 것을 알리면 이미 값이 반이다."""
    assert len(_hits([_offer(t=T - 60, bpc=5.0)] + _peers())) == 1
    assert _hits([_offer(t=T - 61, bpc=5.0)] + _peers()) == []


def test_미래_시각은_안_울린다():
    """되감기·시계 어긋남에서 음수 나이가 나올 수 있다 — 그때 울리면 안 된다."""
    assert _hits([_offer(t=T + 5, bpc=5.0)] + _peers()) == []


# ── 침묵해야 하는 자리 ───────────────────────────────────────────────────────
def test_비드는_안_울린다():
    assert _hits([_offer(s="B", bpc=5.0)] + _peers()) == []


def test_민평에는_안_울린다():
    """부른 값이 없다 — 책의 3분의 2가 여기 있다(실측 67%)."""
    assert _hits([_offer(atmp=True, bpc=5.0)] + _peers()) == []


def test_레벨이_가정이면_안_울린다():
    assert _hits([_offer(lvl="est", bpc=5.0)] + _peers()) == []


def test_무리가_작으면_안_울린다():
    """`PEER_MIN` 미만에서는 중앙값이 뜻이 없다 — `peer_rank` 가 아무 말도 안 한다."""
    assert _hits([_offer(bpc=5.0)] + _peers(KV.PEER_MIN - 2)) == []
    assert len(_hits([_offer(bpc=5.0)] + _peers(KV.PEER_MIN - 1))) == 1


def test_값이_없으면_무리에도_안_들고_안_울린다():
    """뺄 수 없으면 «—» 라는 이 레인 규율 — 0 으로 가정하지 않는다."""
    assert _hits([_offer(bpe=None, bpc=None)] + _peers()) == []


def test_잔존이_없거나_지나면_안_울린다():
    """잔존칸이 없으면 무리가 안 선다. ★잔존 음수 오퍼가 실제로 책에 있다
    (실측 2026-09-03 리플레이: 하나금융지주14 가 −2.51년)."""
    assert _hits([_offer(ttm=None, bpc=5.0)] + _peers()) == []
    assert _hits([_offer(ttm=-2.51, bpc=5.0)] + _peers()) == []


# ── ★★무리는 하나뿐이다 — 잔존 칸을 포함한다 [OWNER 2026-10-01] ──────────────
def test_잔존칸이_무리를_가른다():
    """★이 시험이 2026-10-01 의 수리를 박는다.

    같은 계열·등급이라도 **잔존 칸이 다르면 다른 무리**다. 그 전에는 `cr_buckets`
    (잔존 통째)를 무리로 썼기 때문에 ~1년 또래가 1~2년 오퍼의 기준에 섞여 들어왔다.

    ★또래 수를 **일부러 기울인다**(짧은 쪽 아홉 · 긴 쪽 셋). 반반으로 두면 섞은
      중앙값과 칸별 중앙값이 **우연히 같아져** 이 시험이 아무것도 안 잡는다 — 처음
      그렇게 짰고 잔존 칸을 빼도 21개가 전부 초록이었다(2026-10-01 거짓 초록).
      ▎1~2년 무리의 중앙은 +10 → +12 는 «2bp 싼 것»이라 안 울려야 한다.
      ▎섞으면 중앙이 0 으로 내려가 +12 가 «12bp 싼 것»이 되어 울린다.
    """
    short = _peers(9, bpe=0.0, bpc=0.0, ttm=0.5)         # ~1년 또래 아홉 — 중앙 0
    long_ = [dict(o, n="장기" + o["n"], d="Q" + o["d"])
             for o in _peers(3, bpe=10.0, bpc=10.0, ttm=1.5)]   # 1~2년 또래 셋 — 중앙 +10
    assert _hits([_offer(ttm=1.5, bpe=12.0, bpc=12.0, n="주인공")] + short + long_,
                 n_bp=3.0) == []
    h = _hits([_offer(ttm=1.5, bpe=14.0, bpc=14.0, n="주인공")] + short + long_, n_bp=3.0)
    assert len(h) == 1 and h[0]["dev"] == 4.0 and h[0]["med"] == 10.0


def test_무리에서_잔존이_가장_긴_오퍼도_울린다():
    """★옛 구현은 `ttm_lo <= ttm < ttm_hi` 로 무리를 찾아 **그 무리에서 잔존이 가장 긴
    오퍼가 영원히 못 울렸다**(실측 8/256건 · 그중 하나가 `bpe +17.1` 짜리였다).
    무리가 잔존칸이 된 지금은 그런 배제가 없다."""
    h = _hits([_offer(ttm=0.9, bpc=6.0, n="가장긴것")] + _peers(5, ttm=0.2), n_bp=3.0)
    assert [x["n"] for x in h] == ["가장긴것"]


def test_알람과_화면_배지가_같은_무리를_말한다():
    """★★«대조» — 알람의 `pk`·`pn`·`pr` 은 화면이 「무리 n개 중 k위」로 쓰는 그 값이다.
    알람이 제 무리를 따로 만들면 한 화면이 두 무리를 말한다(2026-10-01 까지 그랬다)."""
    rows = [dict(o) for o in [_offer(bpc=9.0)] + _peers(5)]
    ranks = KV.peer_rank(rows)
    for e in rows:
        e.update(ranks.get(id(e)) or {})
    h = KV.alarm_hits(rows, T, n_bp=3.0)
    me = rows[0]
    assert h[0]["pk"] == me["pk"] == "은행채 AAA ~1년"
    assert h[0]["pn"] == me["pn"] == 6          # 주인공 + 또래 다섯
    assert h[0]["pr"] == me["pr"] == 1          # 가장 싸다
    assert h[0]["med"] == me["pmed"]            # 중앙값도 그 무리의 것


def test_중앙값은_peer_rank_가_낸_것이다():
    """두 곳이 중앙값을 유도하면 한쪽만 고치게 된다 — `pmed` 하나뿐임을 박는다."""
    rows = [dict(o) for o in [_offer(bpc=5.0)] + _peers(5, bpc=2.0, bpe=2.0)]
    ranks = KV.peer_rank(rows)
    for e in rows:
        e.update(ranks.get(id(e)) or {})
    assert rows[0]["pmed"] == 2.0
    assert KV.alarm_hits(rows, T, n_bp=3.0)[0]["med"] == 2.0


# ── ★재는 자가 하나 ─────────────────────────────────────────────────────────
def test_무리가_커브반영을_못_가지면_민평대비로_잰다():
    """섞어서 재지 않는다 — 전원이 가졌을 때만 커브반영으로 잰다(`peer_rank` 의 규칙)."""
    h = _hits([_offer(bpe=6.0, bpc=5.0)] + _peers(5, bpe=1.0, bpc=None), n_bp=3.0)
    assert len(h) == 1
    assert h[0]["adj"] is False
    assert h[0]["val"] == 6.0 and h[0]["med"] == 1.0 and h[0]["dev"] == 5.0


def test_커브반영이_있으면_그것으로_잰다():
    h = _hits([_offer(bpe=9.0, bpc=5.0)] + _peers(5, bpe=0.0, bpc=1.0), n_bp=3.0)
    assert h[0]["adj"] is True and h[0]["dev"] == 4.0   # 5.0 − 1.0, 민평대비가 아니다


# ── 부가 ───────────────────────────────────────────────────────────────────
def test_등급이_집계에서_온_오퍼는_그_사실을_싣는다():
    """★«무리의» 등급이 아니라 **이 오퍼의** 등급이다 — 넓은 무리는 등급을 품어
    하나로 말할 수 없다(2026-10-01 에 뜻을 그렇게 고쳤다)."""
    assert _hits([_offer(bpc=5.0, rt_src="집계")] + _peers(), n_bp=3.0)[0]["est"] is True
    assert _hits([_offer(bpc=5.0)] + _peers(), n_bp=3.0)[0]["est"] is False


def test_열쇠는_같은_도착에_같다():
    """5초 폴이면 한 도착이 최대 12번 보인다 — 소비자가 이 열쇠로 접는다."""
    o = _offer(bpc=5.0)
    k1 = _hits([o] + _peers())[0]["key"]
    k2 = _hits([dict(o)] + _peers())[0]["key"]
    assert k1 == k2


def test_모집단을_거른_것을_넣으면_결과가_줄어든다():
    """⚠모집단은 `cr_ranked` 의 것(거르기 전)이어야 한다. 이 시험은 그 계약을
    말로만 두지 않는다 — 거른 목록을 넣으면 답이 달라지는 것을 박아 둔다."""
    a = _offer(bpc=5.0, n="A", d="H01")
    b = _offer(bpc=7.0, n="B", d="H02", rt="AA+")
    peers_a = _peers(5)
    peers_b = [dict(o, n="B" + o["n"], d="R" + o["d"]) for o in _peers(5, rt="AA+")]
    assert len(_hits([a, b] + peers_a + peers_b, n_bp=3.0)) == 2
    # 「AAA 만」으로 걸러 넣으면 B 의 무리가 사라져 하나를 잃는다
    assert len(_hits([a] + peers_a, n_bp=3.0)) == 1
