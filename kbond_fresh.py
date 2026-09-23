# -*- coding: utf-8 -*-
"""파생 표가 원장보다 뒤졌는지 한 줄로 답한다. [2026-09-16]

    python kbond_fresh.py          # 아침 확인용 · 뒤졌으면 종료코드 1

왜 이 파일이 있는가 — 2026-09-07~09-10 에 16:30 예약 실행이 **넷 다 끊겼는데 아무도
못 봤다.** 원장(parquet)은 들어갔고 파생 표(다리·체결·KIS)만 안 만들어진 상태라 화면은
멀쩡했다. 그때 단 대책은 로그에 «완료 없이 끝남» 경보를 찍는 것이었는데, 09-16 에 보니
그 경보는 (ㄱ) 5일 내내 오탐이었고 (ㄴ) 고쳐 놓아도 **아침 확인이 그 로그를 안 연다.**

그래서 여기서는 «과정» 이 아니라 «상태» 를 잰다.

    과정  직전 실행이 끝났나        ← 로그를 읽어야 알고, PC 가 꺼지면 줄 자체가 없다
    상태  파생 표가 원장만큼 새것인가 ← 파일 넷의 mtime 이면 끝나고, PC 가 꺼진 날도 덮는다

판정은 **하나만** 단단하게 한다 — «파생 표가 원장보다 오래됐다». 이것이 09-07~09-10 의
signature 그대로다. 나머지(원장 나이·직전 실행 결과)는 사람이 보라고 찍기만 하고 판정에
넣지 않는다. 문턱을 지어내면 그 문턱이 다음 오탐이 된다.

★굽는 중에는 울리지 않는다. 오후 갱신은 원장을 먼저 쓰고 파생 표를 45분쯤 뒤에 쓰므로,
  그동안은 «뒤진» 것이 정상이다. 늘 울리는 경보는 안 울리는 경보보다 나쁘다 — 읽는
  사람을 무시하도록 훈련시킨다. 이 파일이 대신하러 온 그 경보가 정확히 그랬다.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(r"C:\Users\infomax\Projects\data\kbond")
LEDGER = BASE / "kbond_structured_data.parquet"
DERIVED = {
    "다리": BASE / "kbond_legs.parquet",
    "체결": BASE / "kbond_fills.parquet",
    "KIS": BASE / "kbond_kis_curve.parquet",
}
TASK = "KBondDailyUpdate"


def mtime(p: Path) -> datetime | None:
    return datetime.fromtimestamp(p.stat().st_mtime) if p.exists() else None


def span(sec: float) -> str:
    sec = int(abs(sec))
    h, m = divmod(sec // 60, 60)
    return f"{h}시간 {m}분" if h else f"{m}분"


def task_state() -> tuple[str, str]:
    """(상태, 직전 실행 한 줄). 스케줄러가 못 잡히면 ('?', 사유)."""
    ps = ("$t = Get-ScheduledTask -TaskName '%s' -ErrorAction Stop; "
          "$i = Get-ScheduledTaskInfo -TaskName '%s'; "
          "\"$($t.State)|$($i.LastRunTime.ToString('yyyy-MM-dd HH:mm'))|"
          "0x{0:X8}\" -f $i.LastTaskResult" % (TASK, TASK))
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=30)
        state, last, code = out.stdout.strip().split("|")
        return state, f"{last} · {code}"
    except Exception as exc:                                     # 스케줄러가 없어도 판정은 돈다
        return "?", f"스케줄러를 못 읽었다({type(exc).__name__})"


def main() -> int:
    led = mtime(LEDGER)
    if led is None:
        print(f"[고장] 원장이 없다 — {LEDGER}")
        return 1

    state, last = task_state()
    now = datetime.now()

    behind = {name: led - t for name, p in DERIVED.items()
              if (t := mtime(p)) is not None and t < led}
    missing = [name for name, p in DERIVED.items() if not p.exists()]

    def row(label: str, body: str) -> str:
        # 한글은 터미널에서 두 칸을 먹는다. 라벨 폭을 «칸» 으로 맞춘다.
        cols = sum(2 if ord(c) > 0x2E80 else 1 for c in label)
        return f"  {label}{' ' * (6 - cols)}{body}"

    print(row("원장", f"{led:%m-%d %H:%M}  ({span((now - led).total_seconds())} 전)"))
    for name, p in DERIVED.items():
        t = mtime(p)
        if t is None:
            print(row(name, "없음"))
        else:
            gap = (led - t).total_seconds()
            mark = f"원장보다 {span(gap)} 뒤" if gap > 0 else "최신"
            print(row(name, f"{t:%m-%d %H:%M}  {mark}"))
    print(row("예약", f"{TASK} {state} · 직전 {last}"))

    if not behind and not missing:
        print("[정상] 파생 표가 원장만큼 새것이다.")
        return 0

    if state == "Running":
        print("[굽는 중] 갱신이 돌고 있다. 원장이 먼저 갱신되고 파생 표가 뒤따르는 정상 구간이다.")
        print("          끝난 뒤에 다시 볼 것.")
        return 0

    if missing:
        print(f"[고장] 파생 표가 아예 없다 — {', '.join(missing)}")
    if behind:
        worst = max(behind.values()).total_seconds()
        print(f"[늦음] 파생 표가 원장보다 오래됐다(최대 {span(worst)}). "
              "화면은 멀쩡해 보이지만 다리·체결·KIS 가 옛것이다.")
    print(f"       → {TASK} 를 한 번 돌리거나 python kbond_daily_update.py")
    return 1


if __name__ == "__main__":
    sys.exit(main())
