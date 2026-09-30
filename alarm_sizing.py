# -*- coding: utf-8 -*-
r"""알람 교정·사이징 — 「문턱 N bp 로 하루 몇 번 울리나」와 「1등 교체는 진짜인가」.

    python alarm_sizing.py --calibrate              한 스냅샷으로 문턱 표를 낸다
    python alarm_sizing.py --watch 2300 out.jsonl   1등 교체를 세고 도착/만료를 가른다

## 왜 이 파일이 있나 [2026-09-30]

[OWNER] 「1등은 호가 올라오면 알람 띄워주는 식으로」에서 시작했는데, **재 보니 방아쇠를
바꿔야 했다.** 이 스크립트가 그 근거를 다시 낼 수 있게 남긴다. 판정과 설계는
`PROMPT_next_2026-09-30-alarm.md`, 수는 `archive/docs/RESULT_alarm_sizing_2026-09-30.md`.

★**읽기만 한다.** 산 백엔드(`:8301`)에 GET 만 걸고 아무것도 안 고친다.

## 두 물음

① **문턱 교정** — 무리 중앙 대비 편차 분포를 내고 문턱별 하루 환산을 표로 낸다.
   계열·등급마다 정상 민평대비가 달라 전역 bp 하나로는 한쪽에서만 울린다. 그래서
   문턱은 **무리 중앙 대비**로 건다(`buckets` 의 `bp_med`·`bpc_med` 가 이미 온다).
   ⚠재는 자는 하나여야 한다 — 무리가 `bpc_med` 를 가지면 `bpc`, 아니면 `bpe`.
   `peer_rank` 와 같은 규칙이다(그쪽 docstring: 「섞어서 재지 않는다」).

② **1등 교체가 진짜인가** — 교체를 «도착»과 «TTL 만료»로 가른다. 새 1등이 직전보다
   **덜 싸면** 아무것도 안 온 것이다(직전 1등이 늙어 죽고 더 나쁜 것이 왕관을 물려받음).
   실측 2026-09-30: 7건 중 **3건(43%)이 그것**이었다 — 책이 나빠졌는데 울릴 참이었다.

## ⚠하루 환산의 근거

`--calibrate` 의 「하루 N건」은 **원장 역사에서 잰 도착 수**(이름+민평+값+오퍼,
하루 중앙 38건 · 541영업일)에 지금 스냅샷의 초과 비율을 곱한 것이다. 스냅샷 하나의
분포를 쓰므로 그날의 국면이 섞인다 — **자릿수만 본다.**
"""
from __future__ import annotations

import bisect
import json
import statistics as st
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8301"
VIEW = BASE + "/api/view?lane=cr"

#: 원장 역사에서 잰 「값 부른 오퍼」 하루 도착 중앙(2024-02~2026-09 · 541영업일).
#: 재려면 `kbond_legs.parquet` 에서 이름+민평+값+SELL 을 하루로 접는다.
ARRIVALS_PER_DAY = 38

#: 무리가 이보다 작으면 순위·중앙값이 뜻이 없다 — `kbond_view.PEER_MIN` 과 같은 값.
PEER_MIN = 4


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _bucket_of(o: dict, buckets: list) -> dict | None:
    """오퍼가 속한 무리 — 계열×등급×잔존칸. `kbond_view` 의 좁은 무리와 같은 키."""
    ttm = o.get("ttm")
    if ttm is None:
        return None
    for x in buckets:
        lo, hi = x.get("ttm_lo"), x.get("ttm_hi")
        if (x.get("cls") == o.get("cls") and x.get("rt") == o.get("rt")
                and lo is not None and hi is not None and lo <= ttm < hi):
            return x
    return None


def deviation(o: dict, b: dict) -> tuple[float, bool] | None:
    """(무리 중앙 대비 편차, 커브반영으로 쟀나). 싸다 = 양수.

    ★재는 자가 하나여야 한다 — 무리가 `bpc_med` 를 가졌고 이 오퍼도 `bpc` 가 있으면
      커브반영으로, 아니면 둘 다 민평대비로. 섞어서 재지 않는다.
    """
    adj = o.get("bpc") is not None and b.get("bpc_med") is not None
    v = o.get("bpc") if adj else o.get("bpe")
    m = b.get("bpc_med") if adj else b.get("bp_med")
    if v is None or m is None:
        return None
    return v - m, adj


def calibrate() -> int:
    d = _get(VIEW)
    bks = d.get("buckets") or []
    devs = []
    for o in d.get("offers") or []:
        if o.get("atmp") or o.get("bpe") is None:
            continue
        b = _bucket_of(o, bks)
        if not b or (b.get("n") or 0) < PEER_MIN:
            continue
        r = deviation(o, b)
        if r:
            devs.append(r[0])
    devs.sort()
    if not devs:
        print("잴 것이 없다 — 책이 비었거나 무리가 다 작다"); return 1
    print(f"무리 중앙 대비 편차 {len(devs)}개 (싸다 = 양수) · 하루 도착 {ARRIVALS_PER_DAY}건 기준")
    if len(devs) >= 100:
        q = st.quantiles(devs, n=100)
        print("  분위: " + " · ".join(f"p{p} {q[p-1]:+.2f}" for p in (10, 25, 50, 75, 90, 95, 99)))
    else:
        print(f"  중앙 {st.median(devs):+.2f} · 최대 {max(devs):+.2f} (표본 {len(devs)} — 분위는 안 낸다)")
    print()
    print(f"  {'문턱':>6s} {'지금 넘는 것':>14s} {'하루 환산':>10s}")
    for N in (1, 2, 3, 5, 7, 10, 15):
        k = len(devs) - bisect.bisect_left(devs, N)
        print(f"  +{N:2d}bp {k:6d}/{len(devs):<6d} ({k/len(devs):5.1%}) {k/len(devs)*ARRIVALS_PER_DAY:8.1f}건")
    return 0


def _ident(o: dict) -> tuple:
    """1등을 가리키는 열쇠 — **레벨을 뺀다**(같은 딜러의 재마크는 교체가 아니다).
    실측 2026-09-30: 원시 교체 9건 중 2건이 재마크였다."""
    return (o.get("nm") or o.get("name"), o.get("dl") or o.get("d"))


def watch(secs: int, out_path: str, every: int = 20) -> int:
    prev: dict = {}
    n = 0
    with open(out_path, "w", encoding="utf-8") as f:
        t0 = time.time()
        while time.time() - t0 < secs:
            try:
                d = _get(VIEW)
            except Exception as exc:                          # noqa: BLE001
                f.write(json.dumps({"t": time.time(), "err": str(exc)}) + "\n"); f.flush()
                time.sleep(every); continue
            n += 1
            tops = {}
            for o in d.get("offers") or []:
                if o.get("pr") == 1:
                    # 무리 키는 라벨이 아니다 — 넓은 무리 fallback 이 라벨에서 등급을 뺀다.
                    tops[(o.get("pk"), o.get("pn"))] = (_ident(o), o.get("bpe"), o.get("bpc"))
            for k, cur in tops.items():
                if k in prev and prev[k][0] != cur[0]:
                    fb, tb = prev[k][1], cur[1]
                    kind = ("arrival" if (fb is not None and tb is not None and tb > fb)
                            else "expiry")     # 덜 싸졌다 = 직전 1등이 사라진 것
                    f.write(json.dumps({"t": time.time(), "ev": "top_changed", "kind": kind,
                                        "grp": k[0], "pn": k[1],
                                        "from": prev[k][:2], "to": cur[:2]},
                                       ensure_ascii=False) + "\n")
            f.write(json.dumps({"t": time.time(), "ev": "poll", "ver": d.get("ver"),
                                "ranked": sum(1 for o in (d.get("offers") or []) if o.get("pr")),
                                "tops": len(tops)}, ensure_ascii=False) + "\n")
            f.flush()
            prev = tops
            time.sleep(every)
    print(f"폴 {n}회 → {out_path}")
    return 0


def main(argv: list[str]) -> int:
    if "--calibrate" in argv:
        return calibrate()
    if "--watch" in argv:
        i = argv.index("--watch")
        return watch(int(argv[i + 1]), argv[i + 2] if len(argv) > i + 2 else "alarm_watch.jsonl")
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
