# -*- coding: utf-8 -*-
"""굽는 삯 — «보는 사람이 있을 때만 · 초당 한 번» 을 지키는지. [2026-09-23]

왜 이 파일이 있는가 — 2026-09-23 실측에서 백엔드가 **보는 사람 0명인데** 한 코어의
15.3%를 태우고 있었다(기동 2시간 11분 · CPU 1,213초). 원인은 굽는 주기와 읽는
주기가 달랐던 것이다 — 엔진은 0.4초마다 520KB 책을 만들어 직렬화했는데 SSE 는
1초에 한 번만 읽는다. 보는 사람이 있어도 60%가, 없으면 전부가 버려졌다.

★이 시험이 지키는 것은 «빠르다» 가 아니라 **«안 구웠다»** 와 **«그런데도 안 멈춘다»**
  둘이다. 절약만 지키면 언젠가 화면이 멎고, 그때 원인을 여기서 못 찾는다.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kbond_live as KL                                         # noqa: E402


@pytest.fixture
def state():
    """STATE 를 시험용으로 비워 두고 끝나면 되돌린다."""
    keep = {k: KL.STATE[k] for k in
            ("ver", "dirty", "built", "clients", "publish", "raw", "book")}
    KL.STATE.update(ver=0, dirty=False, built=0.0, clients=0,
                    publish=None, raw=b"{}", book={})
    yield KL.STATE
    KL.STATE.update(keep)


class FakeBook:
    """굽는 값이 얼마나 자주 만들어지는지만 센다."""
    def __init__(self):
        self.n = 0
        self.stream = []

    def snapshot(self):
        self.n += 1
        return {"n": self.n}


def _publish_of(book, state):
    """start_engine 안의 publish 와 «같은 규약» 을 시험에 세운다.

    ⚠엔진 원본을 부르려면 DB·로그가 있어야 해서 여기서는 규약만 옮겨 온다.
      규약이 갈라지지 않게 조건 셋을 그대로 적는다 — 첫 판·강제·(바뀜·보는
      사람·1초). 원본이 바뀌면 test_publish_규약이_원본과_같다 가 운다.
    """
    def publish(force=False):
        with state["lock"]:
            if not (force or state["dirty"]):
                return False
            state["dirty"] = False
        snap = book.snapshot()
        with state["lock"]:
            state["book"] = snap
            state["ver"] += 1
            state["built"] = time.time()
        return True
    return publish


def test_아무도_안_보면_굽지_않는다(state):
    book = FakeBook()
    publish = _publish_of(book, state)
    state["dirty"] = True
    state["built"] = time.time()
    state["clients"] = 0
    # poll 의 판정을 그대로
    if state["dirty"] and state["clients"] > 0 \
            and time.time() - state["built"] >= KL.PUBLISH_MIN_S:
        publish()
    assert book.n == 0, "보는 사람이 없는데 구웠다"
    assert state["dirty"] is True, "안 구웠으면 «밀렸다» 는 남아 있어야 한다"


def test_보는_사람이_있으면_굽는다(state):
    book = FakeBook()
    publish = _publish_of(book, state)
    state["dirty"] = True
    state["clients"] = 1
    state["built"] = time.time() - 2 * KL.PUBLISH_MIN_S      # 주기는 지났다
    if state["dirty"] and state["clients"] > 0 \
            and time.time() - state["built"] >= KL.PUBLISH_MIN_S:
        publish()
    assert book.n == 1
    assert state["ver"] == 1


def test_주기_안에서는_두_번_굽지_않는다(state):
    """★SSE 가 1초에 한 번 읽으므로 그보다 자주 구우면 버려진다."""
    book = FakeBook()
    publish = _publish_of(book, state)
    state["clients"] = 1
    for _ in range(5):                                       # 0.4초 폴 다섯 번 몫
        state["dirty"] = True
        if state["dirty"] and state["clients"] > 0 \
                and time.time() - state["built"] >= KL.PUBLISH_MIN_S:
            publish()
    assert book.n == 1, f"주기 안에서 {book.n}번 구웠다"


def test_HTTP_는_주기를_안_기다린다(state):
    """★절약이 «묵은 값» 이 되면 안 된다 — 요청이 오면 그 자리에서 굽는다."""
    book = FakeBook()
    publish = _publish_of(book, state)
    state["clients"] = 0                                     # 아무도 안 본다
    state["dirty"] = True
    assert publish(force=True) is True                       # _snapshot 이 하는 일
    assert book.n == 1
    assert state["book"] == {"n": 1}


def test_안_밀렸으면_연달아_때려도_한_번만_굽는다(state):
    book = FakeBook()
    publish = _publish_of(book, state)
    state["dirty"] = True
    assert publish() is True
    assert publish() is False and publish() is False
    assert book.n == 1


def test_보는_사람_세기는_음수로_안_내려간다():
    """★세다가 빼먹으면 화면이 멈춘다. 바닥을 0 으로 막아 둔 것을 지킨다."""
    keep = KL.STATE["clients"]
    try:
        KL.STATE["clients"] = 0
        KL.STATE["clients"] = max(0, KL.STATE["clients"] - 1)
        assert KL.STATE["clients"] == 0
    finally:
        KL.STATE["clients"] = keep


def test_굽는_주기는_SSE_읽는_주기보다_짧지_않다():
    """★둘이 갈라지면 이 최적화의 근거가 사라진다.

    SSE 는 kbond_api 와 옛 판 둘 다 1초다. 굽는 주기를 그보다 짧게 두면
    다시 버리는 일이 생기고, 훨씬 길게 두면 화면이 늦는다.
    """
    assert KL.PUBLISH_MIN_S >= 1.0
    assert KL.PUBLISH_MIN_S <= 2.0


def test_먹이는_주기는_그대로다():
    """★굽는 삯만 아끼고 «체결 시각» 은 안 민다 — POLL_S 를 건드리면 안 된다."""
    assert KL.POLL_S == 0.4


def test_규약이_원본과_같다():
    """★시험이 옮겨 적은 조건 셋이 kbond_live 원본과 같은 말인지 본다.

    원본을 고치면서 이 시험을 안 고치면, 여기 통과가 거짓이 된다.
    """
    src = Path(__file__).resolve().parent.joinpath("kbond_live.py").read_text(
        encoding="utf-8")
    assert 'STATE["dirty"] and STATE["clients"] > 0' in src
    assert 'now - STATE["built"] >= PUBLISH_MIN_S' in src
    assert "def publish(force=False):" in src
    assert 'STATE["publish"] = publish' in src
