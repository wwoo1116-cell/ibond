# -*- coding: utf-8 -*-
"""알람 교정기 단위시험 — 모집단·환산·접기. [설계 `PROMPT_next_2026-09-30-alarm.md`]

    python -m pytest test_alarm_sizing.py -q

서버를 안 띄운다 — 여기서 재는 것은 `alarm_sizing` 의 **순수한 부분**이다.

왜 이 파일이 있는가 [2026-10-01]: 교정기가 알람과 **다른 모집단**을 보고 있었다
(`lvl == "est"` 를 알람은 거르는데 교정기는 안 걸렀다). 그러면 교정해서 고른 문턱이
실제로 울릴 수와 어긋난다. 이 레인이 반복해서 찾은 그 병이라, 말로 적지 않고
**«대조 문»** 으로 박는다 — `test_교정기와_알람이_같은_것을_센다`.
"""
from __future__ import annotations

import json

import alarm_sizing as AS
import kbond_view as KV
from enrich_kbond_quotes import BP_PER_WON, TTM_GRID

T = 50_000          # 기준 시각(자정 이후 초)


def _bucket(cls="은행채", rt="AAA", lo=0.0, hi=1.0, n=8, bp_med=0.0, bpc_med=0.0):
    return {"cls": cls, "rt": rt, "ttm_lo": lo, "ttm_hi": hi, "n": n,
            "bp_med": bp_med, "bpc_med": bpc_med, "est": False}


def _offer(**over):
    o = {"s": "S", "atmp": False, "lvl": None, "t": T - 10, "cls": "은행채",
         "rt": "AAA", "ttm": 0.5, "bpe": 5.0, "bpc": 5.0, "n": "KB국민은행1-1",
         "d": "H01", "a": 100.0}
    o.update(over)
    return o


def _view(offers, buckets=None, t=T):
    return {"t": t, "offers": offers, "buckets": buckets or [_bucket()]}


# ── 환산: 식은 한 곳에만 있다 ───────────────────────────────────────────────
def test_격자_위에서는_실측표_값_그대로다():
    """★표를 베끼지 않았는지 재는 시험이다 — 베꼈으면 한쪽만 고쳐도 초록이 된다."""
    for x, y in zip(TTM_GRID, BP_PER_WON):
        assert abs(AS.bp_per_won(float(x)) - float(y)) < 1e-9


def test_격자_사이는_선형보간이다():
    lo, hi = 0.875, 1.25            # 1.12 · 0.87
    mid = AS.bp_per_won(1.0)
    assert 0.87 < mid < 1.12
    w = (1.0 - lo) / (hi - lo)
    assert abs(mid - (1.12 + w * (0.87 - 1.12))) < 1e-9


def test_표_밖은_역수로_잇는다():
    """`enrich_kbond_quotes.won_to_bp` 와 같은 규약(D_mod≈TTM). ★짧은 쪽에서 가파르다 —
    잔존 0.01년이면 **끝전 1원이 100bp** 다. 이 시험이 그 사실을 박아 둔다."""
    assert abs(AS.bp_per_won(0.01) - 100.0) < 1e-9
    assert abs(AS.bp_per_won(5.0) - 0.2) < 1e-9


def test_잔존이_없거나_0이면_환산을_안_한다():
    assert AS.bp_per_won(None) is None
    assert AS.bp_per_won(0) is None
    assert AS.to_won(3.0, 0) is None


def test_같은_bp가_잔존마다_다른_돈이다():
    """★이 레인의 열린 결정 ②. 3bp 가 잔존 0.01년에선 단가 0.03원, 1년에선 2.89원 —
    **100배**다. 「싼 것」을 bp 하나로만 재면 짧은 잔존이 목록을 먹는다."""
    a, b = AS.to_won(3.0, 0.01), AS.to_won(3.0, 1.0)
    assert abs(a - 0.03) < 1e-9
    assert 2.8 < b < 3.0
    assert b / a > 90


# ── 모집단: 알람이 보는 것과 같아야 한다 ─────────────────────────────────────
def test_값_부른_오퍼는_모집단에_든다():
    rows = AS._pop(_view([_offer()]))
    assert len(rows) == 1
    assert rows[0]["dev"] == 5.0 and rows[0]["age"] == 10


def test_열쇠가_알람의_것과_같다():
    """접는 열쇠가 두 벌이면 `--pool` 의 하루 건수가 알람과 다른 것을 센다."""
    o = _offer()
    a = AS._pop(_view([o]))[0]["key"]
    b = KV.alarm_hits([o], [_bucket()], T, n_bp=3.0)[0]["key"]
    assert a == b


def test_안_울리는_것은_모집단에도_없다():
    """비드 · 「민평에」 · 레벨이 가정 · 작은 무리 — 알람이 거르는 넷 그대로."""
    for over in ({"s": "B"}, {"atmp": True}, {"lvl": "est"}):
        assert AS._pop(_view([_offer(**over)])) == []
    assert AS._pop(_view([_offer()], [_bucket(n=AS.PEER_MIN - 1)])) == []


def test_중앙값이_없으면_모집단에_없다():
    assert AS._pop(_view([_offer(bpe=None)], [_bucket(bp_med=None, bpc_med=None)])) == []


def test_재는_자가_하나다():
    """무리가 커브반영을 못 가지면 둘 다 민평대비로 — `peer_rank` 와 같은 규칙."""
    r = AS._pop(_view([_offer(bpe=6.0, bpc=5.0)], [_bucket(bpc_med=None, bp_med=1.0)]))
    assert r[0]["adj"] is False and r[0]["dev"] == 5.0


def test_교정기와_알람이_같은_것을_센다():
    """★★«대조 문» — 한쪽만 고치면 셋 다 빨개진다.

    같은 책·같은 문턱·같은 나이 창이면 `_pop` 이 고른 것과 `alarm_hits` 가 울린 것이
    **열쇠까지 같아야** 한다. 2026-10-01 이전엔 `est` 하나가 교정기에만 들어 있었다.
    """
    offers = [_offer(n="A", d="H01", bpc=5.0),
              _offer(n="B", d="H02", bpc=9.0),
              _offer(n="C", d="H03", bpc=1.0),          # 문턱 아래
              _offer(n="D", d="H04", bpc=9.0, lvl="est"),   # 가정 레벨
              _offer(n="E", d="H05", bpc=9.0, atmp=True),   # 민평에
              _offer(n="F", d="H06", bpc=9.0, t=T - 999)]   # 늙었다
    bks = [_bucket(bpc_med=0.0)]
    mine = {r["key"] for r in AS._pop(_view(offers, bks))
            if r["dev"] >= 3.0 and r["age"] <= AS.MAX_AGE}
    theirs = {h["key"] for h in KV.alarm_hits(offers, bks, T, n_bp=3.0)}
    assert mine == theirs
    assert len(mine) == 2                      # A·B 만


def test_나이_창과_알람이_같은_값이다():
    assert AS.MAX_AGE == KV.ALARM_MAX_AGE


def test_무리_최소가_알람과_같은_값이다():
    assert AS.PEER_MIN == KV.PEER_MIN


# ── 접기: 한 도착은 한 번 ───────────────────────────────────────────────────
def _write(tmp_path, polls):
    p = tmp_path / "s.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for t, offers in polls:
            f.write(json.dumps({"ev": "poll", "t": t,
                                "rows": AS._pop(_view(offers, [_bucket(bpc_med=0.0)], t))},
                               ensure_ascii=False) + "\n")
    return str(p)


def test_같은_도착을_여러_폴에서_봐도_한_번으로_센다(tmp_path, capsys):
    """20초 폴이면 한 도착이 창 안에서 세 번 보인다 — 세 번 울린 것이 아니다."""
    o = _offer(t=T - 5, bpc=5.0)
    path = _write(tmp_path, [(T, [o]), (T + 20, [o]), (T + 40, [o])])
    assert AS.pool([path]) == 0
    out = capsys.readouterr().out
    assert "도착 1건" in out


def test_나이_창을_넘은_것은_안_센다(tmp_path, capsys):
    o = _offer(t=T - 5, bpc=5.0)
    path = _write(tmp_path, [(T + 600, [o])])          # 창 밖에서만 보였다
    assert AS.pool([path]) == 0
    assert "도착 0건" in capsys.readouterr().out


def test_폴이_없으면_말하고_멈춘다(tmp_path, capsys):
    p = tmp_path / "e.jsonl"
    p.write_text("", encoding="utf-8")
    assert AS.pool([str(p)]) == 1
    assert "폴이 없다" in capsys.readouterr().out


def test_표집_나이_상한이_창보다_넉넉하다():
    """★창과 **같게** 잡으면 나중에 더 긴 창으로 다시 못 돌려 본다(자료를 버린 것)."""
    assert AS.SAMPLE_AGE_CAP > AS.MAX_AGE


def test_폴_간격이_나이_창보다_길면_거부한다(capsys):
    """★길면 도착을 통째로 놓친다 — 조용히 적게 세는 대신 안 돈다."""
    assert AS.sample(1, "x.jsonl", every=AS.MAX_AGE + 1) == 2
    assert "놓친다" in capsys.readouterr().out
