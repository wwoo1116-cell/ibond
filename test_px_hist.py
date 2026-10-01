# -*- coding: utf-8 -*-
"""시세 테이프 «어제까지» 의 규칙 — `kbond_px_hist` 의 순수 조각. [2026-10-01]

재는 것
  ① 분 안에서는 나중 것이 지금(같은 분 두 호가 → 뒤의 것)
  ② 고립 스파이크는 빠지고, 무리째 움직인 것은 안 빠진다
  ③ 민평은 그날 하나(하루 중앙값)
  ④ 자르기 — 마지막 n 영업일 · `before` 앞 · 순번은 0 부터 다시
  ⑤ 오늘 체결은 테이프에서 시간순으로, 레인·종목이 맞는 것만
"""
import pandas as pd
import pytest

import kbond_px_hist as H
import kbond_view as KV


def _row(date, time, side, y, code="26-1", mp=3.945):
    return {"Date": pd.Timestamp(date), "Time": time, "Sector": "국고", "BondCode": code,
            "Position": side, "QuoteYield": y, "MPYieldDB": mp}


def test_분_안에서는_나중_것이_지금():
    df = pd.DataFrame([
        _row("2026-09-30", "10:00:05", "BUY", 3.950),
        _row("2026-09-30", "10:00:40", "BUY", 3.955),
        _row("2026-09-30", "10:00:20", "SELL", 3.940),
    ])
    out = H.collapse(df)
    assert len(out) == 1
    r = out.iloc[0]
    assert (r["code"], r["date"], int(r["m"])) == ("26-1", "2026-09-30", 600)
    assert r["b"] == 3.955 and r["a"] == 3.940


def test_값_없는_행과_스왑은_안_들어온다():
    df = pd.DataFrame([
        _row("2026-09-30", "10:00:05", "BUY", None),
        _row("2026-09-30", "10:01:05", "SWAP", 3.9),
        _row("2026-09-30", "10:02:05", "SELL", 3.94),
    ])
    out = H.collapse(df)
    assert out["m"].tolist() == [602]
    assert pd.isna(out.iloc[0]["b"]) and out.iloc[0]["a"] == 3.94


def test_고립_스파이크는_빠지고_무리는_남는다():
    ys = [3.93, 3.931, 3.932, 4.05, 3.933, 3.934, 3.935]      # 넷째가 12bp 튄다
    s = H.drop_spikes(pd.Series(ys))
    assert pd.isna(s.iloc[3]) and s.notna().sum() == 6
    # 무리째 한 단 올라간 것은 스파이크가 아니다
    step = [3.93, 3.93, 3.93, 3.93, 4.00, 4.00, 4.00, 4.00]
    assert H.drop_spikes(pd.Series(step)).notna().all()
    # 이웃이 셋 미만이면 판단하지 않는다
    assert H.drop_spikes(pd.Series([3.9, 4.5, 3.9])).notna().all()


def test_민평은_그날_하나():
    df = pd.DataFrame([
        _row("2026-09-29", "10:00:00", "BUY", 3.97, mp=3.970),
        _row("2026-09-29", "11:00:00", "SELL", 3.96, mp=3.970),
        _row("2026-09-30", "10:00:00", "BUY", 3.95, mp=3.945),
    ])
    out = H.collapse(df)
    assert out.groupby("date")["mp"].nunique().tolist() == [1, 1]
    assert out[out["date"] == "2026-09-30"]["mp"].iloc[0] == 3.945


def test_자르기_마지막_n일_before_앞_순번은_0부터():
    days = ["2026-09-26", "2026-09-29", "2026-09-30", "2026-10-01"]
    rows = [[0, 600, 3.9, None], [1, 601, 3.91, 3.9], [2, 602, 3.95, 3.94], [3, 603, 3.94, 3.93]]
    mp = [3.90, 3.91, 3.97, 3.945]
    out = H.slice_days(days, rows, mp, n=2, before="2026-10-01")
    assert out["days"] == ["2026-09-29", "2026-09-30"]
    assert out["q"] == [[0, 601, 3.91, 3.9], [1, 602, 3.95, 3.94]]
    assert out["mp"] == [3.91, 3.97]
    # 0 = 전부(before 앞)
    assert H.slice_days(days, rows, mp, n=0, before="2026-10-01")["days"] == days[:3]
    # 아무것도 안 남으면 빈 것
    assert H.slice_days(days, rows, mp, n=5, before="2026-09-01") == {"days": [], "q": [], "mp": []}


def test_오늘_체결은_테이프에서_시간순으로_레인과_종목이_맞는_것만():
    snap = {"tape": [
        {"t": 50000, "lane": "ktb", "code": "26-1", "y": 3.94, "a": 100.0, "d": "DS"},
        {"t": 40000, "lane": "ktb", "code": "26-1", "y": 3.95, "a": None, "d": "키움"},
        {"t": 45000, "lane": "ktb", "code": "26-1", "y": None, "a": 100.0, "d": "확정만"},
        {"t": 46000, "lane": "msb", "code": "26-1", "y": 3.0, "a": None, "d": "다른레인"},
        {"t": 47000, "lane": "ktb", "code": "25-9", "y": 3.5, "a": None, "d": "다른종목"},
        {"t": 60000, "lane": "ktb", "code": "26-1", "y": 3.93, "a": None, "d": "T 뒤"},
    ]}
    out = KV.px_fills(snap, "ktb", "26-1", T=55000)
    assert [e["t"] for e in out] == [40000, 50000]
    assert out[1] == {"t": 50000, "y": 3.94, "a": 100.0, "d": "DS"}


def test_없는_종목은_빈_날들과_이유():
    out = H.hist("없는코드", days=5, before="2026-10-01")
    assert out["days"] == [] and out["q"] == [] and out["note"]
