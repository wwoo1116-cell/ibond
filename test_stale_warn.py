# -*- coding: utf-8 -*-
"""«완료 없이 끝남» 경보 단위시험. [2026-09-16]

    python -m pytest test_stale_warn.py -q

왜 이 파일이 있는가 — 09-11 에 단 경보가 09-16 까지 **한 번도 작동하지 않았다.**
실행 8번 중 경보를 단 7번에서 전부 울렸고, 매번 가리킨 시각이 자기 자신이었다.

    2026-09-16 15:50:01  K-Bond 증분 갱신 시작
    2026-09-16 15:50:01    [경고] 직전 실행이 «완료» 없이 끝났습니다 — 2026-09-16 15:50:01

판정 함수는 멀쩡했다. 틀린 것은 «부르는 순서» 였다 — 시작 줄을 로그에 쓴 뒤에
로그를 읽으니 방금 쓴 제 줄을 직전 실행으로 집었다. 그래서 여기서는 함수의 참·거짓
뿐 아니라 **main 안의 순서**까지 못 박는다(§3 「판정을 고쳤으면 쓰는 자리를 전부 세라」).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import kbond_daily_update as KDU                                 # noqa: E402


HEAD = "=" * 66
RUN = "2026-09-16 08:05:02  K-Bond 증분 갱신 시작"
FIN = "2026-09-16 09:01:05    완료 3,364초"


def write_log(tmp_path, lines: list[str], monkeypatch) -> Path:
    p = tmp_path / "kbond_daily_update.log"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(KDU, "LOG", p)
    return p


# ── 1. 판정 자체 ─────────────────────────────────────────────────────
def test_완료로_끝났으면_조용하다(tmp_path, monkeypatch):
    write_log(tmp_path, [HEAD, RUN, FIN], monkeypatch)
    assert KDU.prior_unfinished() is None


def test_완료_없이_끊겼으면_그_시작줄을_준다(tmp_path, monkeypatch):
    write_log(tmp_path, [HEAD, RUN], monkeypatch)
    assert KDU.prior_unfinished() == RUN


def test_끊긴_뒤_한_번_돌았으면_다시_조용해진다(tmp_path, monkeypatch):
    """경보는 «직전» 한 번만 본다. 끊긴 실행이 뒤에 완료로 덮이면 해제된다."""
    later = "2026-09-16 15:50:01  K-Bond 증분 갱신 시작"
    write_log(tmp_path, [HEAD, RUN, HEAD, later,
                         "2026-09-16 16:46:12    완료 3,371초"], monkeypatch)
    assert KDU.prior_unfinished() is None


def test_여러_번_끊겼으면_마지막_것을_가리킨다(tmp_path, monkeypatch):
    later = "2026-09-16 15:50:01  K-Bond 증분 갱신 시작"
    write_log(tmp_path, [HEAD, RUN, HEAD, later], monkeypatch)
    assert KDU.prior_unfinished() == later


def test_로그가_없으면_조용하다(tmp_path, monkeypatch):
    monkeypatch.setattr(KDU, "LOG", tmp_path / "없는파일.log")
    assert KDU.prior_unfinished() is None


def test_완료_판정이_다른_줄에_걸리지_않는다(tmp_path, monkeypatch):
    """'완료' 라는 두 글자는 본문에도 나온다. 세는 것은 «들여쓴 완료 줄» 이다."""
    write_log(tmp_path, [HEAD, RUN,
                         "2026-09-16 08:06:00  재파싱 완료를 기다리는 중"], monkeypatch)
    assert KDU.prior_unfinished() == RUN


# ── 2. ★회귀 — 부르는 순서 ───────────────────────────────────────────
#   이 레인을 09-11~09-16 동안 속인 것이 바로 이 순서다. 함수가 아니라 순서가
#   불변식이므로 소스에서 직접 센다.
def test_시작줄을_쓰기_전에_읽는다():
    src = Path(KDU.__file__).read_text(encoding="utf-8").splitlines()

    def only(needle: str) -> int:
        hit = [i for i, ln in enumerate(src) if needle in ln
               and not ln.lstrip().startswith(("#", "def "))]
        assert len(hit) == 1, f"{needle!r} 가 {len(hit)}줄에 있다 — 시험을 고쳐라"
        return hit[0]

    read = only("prior_unfinished()")
    start = only('say("K-Bond 증분 갱신 시작")')
    assert read < start, (
        "경보가 제 시작 줄을 직전 실행으로 집는다 — 09-11~09-16 의 그 버그다. "
        f"읽기 {read + 1}행 > 쓰기 {start + 1}행"
    )


def test_경보를_울리는_자리는_읽는_자리보다_뒤다():
    """경보 문구는 «시작» 줄 아래에 찍혀야 읽는 사람이 어느 실행인지 안다."""
    src = Path(KDU.__file__).read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(src) if 'say("K-Bond 증분 갱신 시작")' in ln)
    emit = next(i for i, ln in enumerate(src) if "[경고] 직전 실행이" in ln and "say(" in ln)
    assert emit > start


# ── 3. 옛 이름이 남아 있지 않은지 ────────────────────────────────────
def test_옛_이름은_사라졌다():
    assert not hasattr(KDU, "warn_if_unfinished"), (
        "warn_if_unfinished 가 남아 있다 — 두 벌이 되면 어느 쪽이 도는지 모른다"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
