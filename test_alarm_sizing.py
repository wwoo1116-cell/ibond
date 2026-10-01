# -*- coding: utf-8 -*-
"""알람 교정기 단위시험 — 모집단·환산·접기. [설계 `PROMPT_next_2026-09-30-alarm.md`]

    python -m pytest test_alarm_sizing.py -q

서버를 안 띄운다 — 여기서 재는 것은 `alarm_sizing` 의 **순수한 부분**이다.

왜 이 파일이 있는가 [2026-10-01]: 교정기가 알람과 **다른 모집단**을 보고 있었다
(`lvl == "est"` 를 알람은 거르는데 교정기는 안 걸렀다). 그러면 교정해서 고른 문턱이
실제로 울릴 수와 어긋난다. 이 레인이 반복해서 찾은 그 병이라, 말로 적지 않고
**«대조 문»** 으로 박는다 — `test_교정기와_알람이_같은_것을_센다`.

★★그 대조 문이 같은 날 한 번 더 일했다. [OWNER] 「잔존 칸을 넣는다」로 알람의 무리가
`cr_buckets`(계열×등급·잔존 통째) → `peer_rank`(계열×등급×**잔존칸**) 로 바뀌자
**이 시험이 즉시 빨개졌다** — 교정기가 여전히 옛 무리를 재고 있었기 때문이다.
그래서 교정기는 이제 무리를 **만들지 않고** 서버가 실어 보내는 `pmed`·`padj` 를 읽는다.
"""
from __future__ import annotations

import json

import alarm_sizing as AS
import kbond_view as KV
from enrich_kbond_quotes import BP_PER_WON, TTM_GRID

T = 50_000          # 기준 시각(자정 이후 초)


def _offer(**over):
    o = {"s": "S", "atmp": False, "lvl": None, "t": T - 10, "cls": "은행채",
         "rt": "AAA", "ttm": 0.5, "bpe": 5.0, "bpc": 5.0, "n": "KB국민은행1-1",
         "d": "H01", "a": 100.0, "rt_src": "문면"}
    o.update(over)
    return o


def _peers(n=5, bpe=0.0, bpc=0.0, **over):
    """무리를 채우는 또래. 창(60초) 밖·TTL 안에 둔다 — 무리는 세우고 스스로는 안 울린다."""
    return [_offer(n=f"또래{i}", d=f"P{i:02d}", bpe=bpe, bpc=bpc, t=T - 600, **over)
            for i in range(n)]


def _ranked(offers):
    """`cr_ranked` 가 하는 일 — 또래 순위·중앙값(`pmed`)·재는 자(`padj`)를 얹는다.
    ★시험이 무리를 손으로 만들지 않는다. 그래야 「교정기가 알람과 같은 무리를 보는가」가
      시험에 **드러난다**(안 그러면 무리를 바꿔도 전부 초록이다 — 2026-10-01 실측)."""
    rows = [dict(o) for o in offers]
    ranks = KV.peer_rank(rows)
    for e in rows:
        e.update(ranks.get(id(e)) or {})
    return rows


def _view(offers, t=T):
    """★페이로드의 시계는 대문자 `T` 다(«자정 이후 초»). 소문자 `t` 는 **없는 열쇠**다."""
    rows = _ranked(list(offers) + _peers())
    return {"T": t, "now": "13:53:20", "offers": rows}


def _subject(rows, key_d="H01"):
    """주인공(또래가 아닌 것) 한 줄을 집어낸다."""
    return [r for r in rows if str(r.get("key", "")).startswith(key_d + "|")]


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
    me = _subject(rows)
    assert len(me) == 1
    assert me[0]["dev"] == 5.0 and me[0]["age"] == 10


def test_열쇠가_알람의_것과_같다():
    """접는 열쇠가 두 벌이면 `--pool` 의 하루 건수가 알람과 다른 것을 센다."""
    rows = _ranked([_offer()] + _peers())
    a = _subject(AS._pop({"T": T, "offers": rows}))[0]["key"]
    b = KV.alarm_hits(rows, T, n_bp=3.0)[0]["key"]
    assert a == b


def test_안_울리는_것은_모집단에도_없다():
    """비드 · 「민평에」 · 레벨이 가정 — 알람이 거르는 셋 그대로."""
    for over in ({"s": "B"}, {"atmp": True}, {"lvl": "est"}):
        assert _subject(AS._pop(_view([_offer(**over)]))) == []


def test_무리가_작으면_모집단에_없다():
    """`PEER_MIN` 미만이면 `peer_rank` 가 아무 말도 안 하고 `pmed` 가 없다."""
    small = _ranked([_offer()] + _peers(KV.PEER_MIN - 2))
    assert AS._pop({"T": T, "offers": small}) == []


def test_값이_없으면_모집단에_없다():
    """뺄 수 없으면 «—» 라는 이 레인 규율 — 0 으로 가정하지 않는다."""
    assert _subject(AS._pop(_view([_offer(bpe=None, bpc=None)]))) == []


def test_교정기는_무리를_다시_만들지_않는다():
    """★`pmed` 가 없으면 못 센다 — 교정기가 무리를 스스로 세우면 이 시험이 초록이 된다."""
    rows = _ranked([_offer()] + _peers())
    for e in rows:
        e.pop("pmed", None)
    assert AS._pop({"T": T, "offers": rows}) == []


def test_재는_자가_하나다():
    """무리가 커브반영을 못 가지면 둘 다 민평대비로 — `peer_rank` 의 규칙."""
    rows = _ranked([_offer(bpe=6.0, bpc=5.0)] + _peers(5, bpe=1.0, bpc=None))
    me = _subject(AS._pop({"T": T, "offers": rows}))[0]
    assert me["adj"] is False and me["dev"] == 5.0      # 6.0 − 1.0, 커브반영이 아니다


def test_교정기와_알람이_같은_것을_센다():
    """★★«대조 문» — 한쪽만 고치면 둘 다 빨개진다.

    같은 책·같은 문턱·같은 나이 창이면 `_pop` 이 고른 것과 `alarm_hits` 가 울린 것이
    **열쇠까지 같아야** 한다. 2026-10-01 에 이 문이 두 번 일했다 — ①`est` 가 교정기에만
    들어 있던 것, ②알람의 무리가 잔존칸을 품게 바뀌었는데 교정기는 옛 무리를 재던 것.
    """
    offers = [_offer(n="A", d="H01", bpc=5.0),
              _offer(n="B", d="H02", bpc=9.0),
              _offer(n="C", d="H03", bpc=1.0),              # 문턱 아래
              _offer(n="D", d="H04", bpc=9.0, lvl="est"),   # 가정 레벨
              _offer(n="E", d="H05", bpc=9.0, atmp=True),   # 민평에
              _offer(n="F", d="H06", bpc=9.0, t=T - 999)]   # 늙었다
    rows = _ranked(offers + _peers())
    mine = {r["key"] for r in AS._pop({"T": T, "offers": rows})
            if r["dev"] >= 3.0 and r["age"] <= AS.MAX_AGE}
    theirs = {h["key"] for h in KV.alarm_hits(rows, T, n_bp=3.0)}
    assert mine == theirs
    assert len(mine) == 2                      # A·B 만


def test_나이_창과_알람이_같은_값이다():
    assert AS.MAX_AGE == KV.ALARM_MAX_AGE


def test_무리_최소가_알람과_같은_값이다():
    assert AS.PEER_MIN == KV.PEER_MIN


# ── ★★시계: 페이로드의 `T` 하나뿐 ───────────────────────────────────────────
def test_시계는_페이로드의_대문자_T_다():
    """★★2026-10-01 에 여기서 틀렸다 — `d["t"]` 를 봤는데 그런 열쇠가 **없다**.

    `kbond_view.view` 가 싣는 것은 `T`(= `now` 를 자정 이후 초로 쪼갠 값)이고, 그것도
    **책의 시계**라 벽시계와 1분쯤 어긋난다(실측 08:20 에 T=30018 대 벽시계 30084).
    """
    me = _subject(AS._pop({"T": T, "offers": _ranked([_offer(t=T - 10)] + _peers())}))
    assert me[0]["age"] == 10


def test_시계가_없으면_벽시계로_떨어지지_않는다():
    """⚠조용한 대체가 틀린 축을 그럴듯하게 만든 자리다 — 나이가 17억 초가 되어
    **하루 종일 0행**을 적을 뻔했다. 축이 없으면 «없다» 고 말한다."""
    me = _subject(AS._pop({"offers": _ranked([_offer()] + _peers())}))   # T 가 없다
    assert me and me[0]["age"] is None


def test_소문자_t_는_시계가_아니다():
    """에포크가 실려 와도 그걸 나이의 축으로 쓰면 안 된다."""
    me = _subject(AS._pop({"t": 1790810412.0,
                           "offers": _ranked([_offer()] + _peers())}))
    assert me and me[0]["age"] is None


def test_표집이_시계_없는_페이로드를_만나면_멈춘다(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(AS, "_get", lambda url: {"offers": []})
    p = tmp_path / "s.jsonl"
    assert AS.sample(1, str(p), every=5) == 3
    assert "`T` 가 없다" in capsys.readouterr().out


# ── 접기: 한 도착은 한 번 ───────────────────────────────────────────────────
def _write(tmp_path, polls):
    p = tmp_path / "s.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for t, offers in polls:
            # 축이 둘이다 — 날 가르기는 벽시계 `wt`, 나이는 책의 `T`.
            f.write(json.dumps({"ev": "poll", "T": t, "wt": 1790810412.0 + t,
                                "rows": AS._pop(_view(offers, t))},
                               ensure_ascii=False) + "\n")
    return str(p)


def test_같은_도착을_여러_폴에서_봐도_한_번으로_센다(tmp_path, capsys):
    """20초 폴이면 한 도착이 창 안에서 세 번 보인다 — 세 번 울린 것이 아니다."""
    o = _offer(t=T - 5, bpc=5.0)
    path = _write(tmp_path, [(T, [o]), (T + 20, [o]), (T + 40, [o])])
    assert AS.pool([path]) == 0
    out = capsys.readouterr().out
    assert "도착 1건" in out
    # ★날 가르기가 벽시계여야 한다 — 책의 `T`(자정 이후 초)로 가르면 전부 1970년이 된다.
    assert "2026-10-01" in out


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
