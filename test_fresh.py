# -*- coding: utf-8 -*-
"""파생 표 신선도 점검 단위시험. [2026-09-16]

    python -m pytest test_fresh.py -q

파일을 진짜로 만들고 mtime 을 손으로 박아 넣는다. 스케줄러는 부르지 않는다
(`task_state` 를 갈아 끼운다) — 시험이 이 PC 의 예약 상태에 딸려 다니면 안 된다.

★여기서 제일 중요한 시험은 «굽는 중에는 안 울린다» 다. 이 파일이 대신하러 온 경보가
  바로 늘 울려서 죽은 경보였다([[test_stale_warn]]).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import kbond_fresh as KF                                         # noqa: E402


NOW = time.time()
HOUR = 3600.0


def build(tmp_path, ledger_age_h: float, derived_age_h: float | None,
          state: str, monkeypatch) -> None:
    """원장 하나 + 파생 표 셋을 만들고 나이를 박는다. derived_age_h=None 이면 안 만든다."""
    led = tmp_path / "kbond_structured_data.parquet"
    led.write_bytes(b"x")
    os.utime(led, (NOW - ledger_age_h * HOUR,) * 2)
    monkeypatch.setattr(KF, "LEDGER", led)

    derived = {}
    for name, fn in (("다리", "kbond_legs.parquet"),
                     ("체결", "kbond_fills.parquet"),
                     ("KIS", "kbond_kis_curve.parquet")):
        p = tmp_path / fn
        if derived_age_h is not None:
            p.write_bytes(b"x")
            os.utime(p, (NOW - derived_age_h * HOUR,) * 2)
        derived[name] = p
    monkeypatch.setattr(KF, "DERIVED", derived)
    monkeypatch.setattr(KF, "task_state", lambda: (state, "2026-09-16 15:50 · 0x00041301"))


# ── 1. 정상 ──────────────────────────────────────────────────────────
def test_파생표가_원장보다_새것이면_정상(tmp_path, monkeypatch, capsys):
    build(tmp_path, ledger_age_h=2.0, derived_age_h=1.0, state="Ready", monkeypatch=monkeypatch)
    assert KF.main() == 0
    assert "[정상]" in capsys.readouterr().out


def test_같은_시각이어도_정상(tmp_path, monkeypatch, capsys):
    build(tmp_path, ledger_age_h=1.0, derived_age_h=1.0, state="Ready", monkeypatch=monkeypatch)
    assert KF.main() == 0
    assert "[정상]" in capsys.readouterr().out


# ── 2. ★굽는 중에는 울리지 않는다 ────────────────────────────────────
def test_굽는_중에는_뒤져_있어도_안_울린다(tmp_path, monkeypatch, capsys):
    """오후 갱신은 원장을 먼저 쓰고 파생 표를 45분쯤 뒤에 쓴다. 그 구간이 정상이다."""
    build(tmp_path, ledger_age_h=0.5, derived_age_h=7.0, state="Running", monkeypatch=monkeypatch)
    assert KF.main() == 0
    out = capsys.readouterr().out
    assert "[굽는 중]" in out and "[늦음]" not in out


# ── 3. ★09-07~09-10 재현 — 이걸 못 잡으면 이 파일은 있을 값이 없다 ──
def test_원장만_들어가고_파생표가_안_만들어진_날(tmp_path, monkeypatch, capsys):
    """원장은 어제 16:30 에 들어갔는데 파생 표는 그 전날 것 — 화면은 멀쩡했다."""
    build(tmp_path, ledger_age_h=16.0, derived_age_h=40.0, state="Ready", monkeypatch=monkeypatch)
    assert KF.main() == 1
    out = capsys.readouterr().out
    assert "[늦음]" in out
    assert "24시간" in out                          # 40 − 16


def test_PC_가_꺼져_있던_날도_잡는다(tmp_path, monkeypatch, capsys):
    """로그 경보가 제 주석에서 못 한다고 인정한 경우 — 줄이 아예 안 남는 날."""
    build(tmp_path, ledger_age_h=72.0, derived_age_h=96.0, state="Ready", monkeypatch=monkeypatch)
    assert KF.main() == 1
    assert "[늦음]" in capsys.readouterr().out


# ── 4. 없는 파일 ─────────────────────────────────────────────────────
def test_파생표가_아예_없으면_고장(tmp_path, monkeypatch, capsys):
    build(tmp_path, ledger_age_h=1.0, derived_age_h=None, state="Ready", monkeypatch=monkeypatch)
    assert KF.main() == 1
    assert "[고장]" in capsys.readouterr().out


def test_원장이_없으면_고장(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(KF, "LEDGER", tmp_path / "없는파일.parquet")
    assert KF.main() == 1
    assert "[고장]" in capsys.readouterr().out


# ── 5. 스케줄러를 못 읽어도 판정은 돈다 ──────────────────────────────
def test_스케줄러를_못_읽어도_늦음은_늦음이다(tmp_path, monkeypatch, capsys):
    build(tmp_path, ledger_age_h=16.0, derived_age_h=40.0, state="?", monkeypatch=monkeypatch)
    assert KF.main() == 1
    assert "[늦음]" in capsys.readouterr().out


# ── 6. 표시 ──────────────────────────────────────────────────────────
def test_span_읽기(tmp_path):
    assert KF.span(90) == "1분"
    assert KF.span(3600) == "1시간 0분"
    assert KF.span(24 * 3600 + 55 * 60) == "24시간 55분"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
