# -*- coding: utf-8 -*-
r"""알람 교정·사이징 — 「문턱 N bp 로 하루 몇 번 울리나」와 「1등 교체는 진짜인가」.

    python alarm_sizing.py --calibrate              한 스냅샷으로 문턱 표를 낸다
    python alarm_sizing.py --watch 2300 out.jsonl   1등 교체를 세고 도착/만료를 가른다
    python alarm_sizing.py --sample 3600 s.jsonl    ★여러 시각을 모은다(하루 내내 돌린다)
    python alarm_sizing.py --pool s.jsonl [s2 ...]  ★모은 것을 «직접 센 하루 건수» 로
    ... --port 8303                                 리플레이 서버를 보게 한다(검증용)

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

★**한 스냅샷으로 문턱을 정하지 말 것** — 2026-09-30 실측에서 25분 차의 두 스냅샷이
+3bp 를 하루 4.5건과 2.3건으로 갈랐다. 그래서 `--sample`/`--pool` 을 붙였다(아래).

## `--sample` / `--pool` — 왜 붙였나 [2026-10-01]

`--calibrate` 는 **한 순간의 책**을 본다. 문턱을 정하려면 여러 시각·여러 날이 필요하고,
그때는 «비율 × 도착 38건» 이라는 대리 지표를 쓸 필요도 없다 — 모아서 **도착을 직접
세면** 된다.

    --sample <초> <파일> [폴초]   폴마다 «자격 있는 오퍼» 를 한 줄씩 붙인다(이어쓰기)
    --pool   <파일...>            나이 창 안의 것만 남기고 도착 열쇠로 접어 하루로 센다

★접는 열쇠는 `kbond_view.alarm_hits` 의 것과 **같다**(`딜러|종목|도착초`) — 같은 수를
  두 곳이 유도하면 한쪽만 고치게 된다. 그쪽 주석: 「5초 폴이면 한 도착이 최대 12번 보인다」.
★폴 간격은 **나이 창(60초)보다 짧아야** 한다. 길면 도착을 통째로 놓친다.

## ⚠모집단 — `alarm_hits` 와 같아야 한다 [2026-10-01 수리]

이 파일의 `calibrate()` 가 **`lvl == "est"` 를 안 걸렀다**. 알람은 거른다
(`alarm_hits`: 「레벨이 가정(`lvl == "est"`) — 0.5 가정 위에서는 안 울린다」).
모집단이 다르면 교정한 문턱이 실제로 울릴 수와 어긋난다 — 이 레인이 반복해서 찾은
그 병이다(「같은 수를 두 곳이 유도하면 한 곳으로 모은다」). `_pop()` 한 곳으로 모았다.

## 잔존 — 「그 bp 는 돈으로 얼마인가」 [2026-10-01]

문턱 3bp 의 1등이 **잔존 0.01년에 +31.8bp** 였다(단가로 0.3원). bp 는 짧은 잔존에서
돈이 아니다 — `to_won()` 이 리포의 실측표로 환산해 표에 같이 적는다. 원장 전체로 잰
분포는 `alarm_ttm.py`, 수는 `archive/docs/RESULT_alarm_ttm_2026-10-01.md`.
"""
from __future__ import annotations

import bisect
import collections
import datetime as dt
import json
import statistics as st
import sys
import time
import urllib.request

#: 원↔bp 환산의 실측표. **여기 베끼지 않는다** — 두 벌로 두면 한쪽만 고치게 된다.
from enrich_kbond_quotes import BP_PER_WON, TTM_GRID

BASE = "http://127.0.0.1:8301"
VIEW = BASE + "/api/view?lane=cr"


def use_port(port: int) -> None:
    """다른 포트를 보게 한다 — **검증은 리플레이 서버를 따로 띄워** 한다는 레인 규율용
    (`set KBOND_REPLAY=… && uvicorn kbond_api:app --port 8303`). 프로덕션 :8301 을 안 건드린다."""
    global BASE, VIEW
    BASE = f"http://127.0.0.1:{port}"
    VIEW = BASE + "/api/view?lane=cr"

#: 원장 역사에서 잰 「값 부른 오퍼」 하루 도착 중앙(2024-02~2026-09 · 541영업일).
#: 재려면 `kbond_legs.parquet` 에서 이름+민평+값+SELL 을 하루로 접는다.
ARRIVALS_PER_DAY = 38

#: 무리가 이보다 작으면 순위·중앙값이 뜻이 없다 — `kbond_view.PEER_MIN` 과 같은 값.
PEER_MIN = 4

#: 「방금 왔다」의 창(초) — `kbond_view.ALARM_MAX_AGE` 와 같은 값(1분 벼랑).
MAX_AGE = 60


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def bp_per_won(ttm):
    """잔존 -> bp/원. `enrich_kbond_quotes.won_to_bp` 의 안쪽과 같다(표 밖은 1/TTM).

    ★표는 0.125~2.50년만 실측이다. 그 밖은 D_mod≈TTM 로 잇는데, **짧은 쪽에서
      1/TTM 은 가파르다** — 잔존 0.014년이면 끝전 1원이 71bp 다. 「짧은 잔존의 큰 bp」
      는 대개 여기서 온다(`alarm_ttm.py` 【B】: 잔존<0.1년 견적의 95.9%가 원 단위).
    """
    if ttm is None or ttm <= 0:
        return None
    grid = [float(x) for x in TTM_GRID]
    vals = [float(x) for x in BP_PER_WON]
    if ttm < grid[0] or ttm > grid[-1]:
        return 1.0 / ttm
    i = bisect.bisect_left(grid, ttm)
    if i == 0:
        return vals[0]
    x0, x1, y0, y1 = grid[i - 1], grid[i], vals[i - 1], vals[i]
    return y0 + (ttm - x0) / (x1 - x0) * (y1 - y0)


def to_won(dev_bp, ttm):
    """무리 중앙 대비 편차(bp) -> 단가 원(액면 1만원). 「그 bp 는 돈으로 얼마인가」.

    100억을 그 값에 사면 버는 돈 = 이 수 × 1e6 원.
    """
    r = bp_per_won(ttm)
    return None if not r else dev_bp / r


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


def _pop(d: dict, T=None) -> list[dict]:
    """교정의 모집단 — **`kbond_view.alarm_hits` 가 보는 것과 같은 것**을 본다.

    울리지 않는 것은 세지도 않는다: 비드 · 「민평에」 · 레벨이 가정(`est`) ·
    무리가 작다 · 중앙값이 없다. (2026-10-01 이전 이 함수가 없어 `est` 가 섞였다.)

    ★★**시계는 페이로드의 `T` 다 — 벽시계가 아니다.** `T` 는 «자정 이후 초»이고
      (`kbond_view.view`: `now` 를 시·분·초로 쪼갠 값), 그것도 **책의 시계**라 벽시계와
      1분쯤 어긋난다(실측 2026-10-01 08:20: T=30018 대 벽시계 30084). 오퍼의 `t` 도
      같은 축이므로 나이는 `T − t` 여야 한다.
    ⚠**대체하지 않는다.** 처음 이 함수는 `d.get("t")`(페이로드에 **없는 열쇠**)를 보고
      `time.time()` 으로 떨어졌고, 그러면 나이가 17억 초가 되어 **하루 종일 0행**을
      적는다. 축이 없으면 조용히 다른 축을 쓰는 대신 **없다고 말한다**.
    """
    bks = d.get("buckets") or []
    T = d.get("T") if T is None else T
    out = []
    for o in d.get("offers") or []:
        if o.get("s") not in (None, "S") or o.get("atmp") or o.get("lvl") == "est":
            continue
        if o.get("bpe") is None or o.get("ttm") is None:
            continue
        b = _bucket_of(o, bks)
        if not b or (b.get("n") or 0) < PEER_MIN:
            continue
        r = deviation(o, b)
        if not r:
            continue
        t = o.get("t")
        out.append({
            # ★`alarm_hits` 의 열쇠와 같다 — 한 도착을 여러 폴에서 봐도 한 번으로 접는다.
            "key": f"{o.get('d')}|{o.get('n')}|{t}",
            "n": o.get("n"), "cls": o.get("cls"), "rt": o.get("rt"),
            "ttm": o.get("ttm"), "dev": round(r[0], 2), "adj": r[1],
            "t": t, "age": (None if (t is None or T is None) else round(T - t, 1)),
        })
    return out


def _ttm_table(recs: list, n_bp: float = 3.0) -> None:
    """잔존별로 갈라 본다 — 「짧은 잔존의 큰 bp 는 돈이 아니다」(`alarm_ttm.py`)."""
    edges = [(0, 0.05), (0.05, 0.25), (0.25, 0.5), (0.5, 1), (1, 2), (2, 3), (3, 99)]
    print(f"\n  잔존별 (문턱 +{n_bp:g}bp 기준) — 「그 bp 는 단가 몇 원인가」")
    print(f"  {'잔존(년)':>10s} {'n':>6s} {'중앙 dev':>9s} {'>=문턱':>7s} "
          f"{'넘은 것 중앙 단가':>18s} {'100억에':>14s}")
    for lo, hi in edges:
        g = [r for r in recs if r["ttm"] is not None and lo <= r["ttm"] < hi]
        if not g:
            continue
        hit = [r for r in g if r["dev"] >= n_bp]
        wons = [w for w in (to_won(r["dev"], r["ttm"]) for r in hit) if w is not None]
        mw = st.median(wons) if wons else None
        band = f"{lo}~{hi}"
        sw = f"{mw:.2f}원" if mw is not None else "—"
        sm = f"{mw * 1e6:,.0f}원" if mw is not None else "—"
        print(f"  {band:>10s} {len(g):6d} {st.median(r['dev'] for r in g):+9.2f} "
              f"{len(hit) / len(g):6.1%} {sw:>18s} {sm:>14s}")


def calibrate() -> int:
    d = _get(VIEW)
    recs = _pop(d)
    devs = sorted(r["dev"] for r in recs)
    if not devs:
        print("잴 것이 없다 — 책이 비었거나 무리가 다 작다")
        return 1
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
        print(f"  +{N:2d}bp {k:6d}/{len(devs):<6d} ({k/len(devs):5.1%}) "
              f"{k/len(devs)*ARRIVALS_PER_DAY:8.1f}건")
    _ttm_table(recs)
    print("\n  ⚠한 스냅샷이다 — 문턱은 `--sample`/`--pool` 로 여러 시각을 모아 정한다.")
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


#: 표집이 남기는 나이 상한(초) — 창의 두 배. `pool` 이 어차피 `MAX_AGE` 로 거르므로
#: 그보다 늙은 행은 파일만 불린다(하루 표집이 수십 MB 대 1MB 미만으로 갈린다).
#: ★창의 **두 배**인 이유: `--pool` 을 나중에 더 긴 창으로 다시 돌려 볼 여지를 남긴다.
SAMPLE_AGE_CAP = 2 * MAX_AGE


def sample(secs: int, out_path: str, every: int = 20,
           age_cap: int = SAMPLE_AGE_CAP) -> int:
    """폴마다 «방금 온 자격 있는 오퍼» 를 한 줄씩 **이어쓴다**. 여러 날 쌓아도 된다.

    ★`every` 는 나이 창(`MAX_AGE`)보다 짧아야 한다 — 길면 도착을 통째로 놓친다.
    ★덮어쓰지 않는다(`a`) — 하루를 여러 번 나눠 돌려도 모인다.
    ★`age_cap` 보다 늙은 행은 안 적는다(§`SAMPLE_AGE_CAP`). 폴 수는 그대로 적으므로
      `--pool` 의 «덮은 시간» 은 안 망가진다.
    """
    if every > MAX_AGE:
        print(f"⚠폴 간격 {every}초가 나이 창 {MAX_AGE}초보다 길다 — 도착을 놓친다")
        return 2
    n = err = 0
    with open(out_path, "a", encoding="utf-8") as f:
        t0 = time.time()
        while time.time() - t0 < secs:
            try:
                d = _get(VIEW)
            except Exception as exc:                          # noqa: BLE001
                err += 1
                f.write(json.dumps({"ev": "err", "t": time.time(), "m": str(exc)}) + "\n")
                f.flush(); time.sleep(every); continue
            n += 1
            T = d.get("T")
            if T is None:
                # ★대체하지 않는다 — 벽시계로 떨어지면 나이가 17억 초가 되고
                #   하루 종일 0행을 적는다(2026-10-01 에 그럴 뻔했다).
                print("⚠페이로드에 `T` 가 없다 — 나이를 잴 축이 없어 멈춘다")
                f.write(json.dumps({"ev": "err", "wt": time.time(),
                                    "m": "no T in payload"}) + "\n")
                return 3
            rows = [r for r in _pop(d, T)
                    if r["age"] is not None and 0 <= r["age"] <= age_cap]
            # `T` 는 책의 «자정 이후 초» 라 날짜가 없다 — 날 가르기는 벽시계(`wt`)로 한다.
            f.write(json.dumps({"ev": "poll", "T": T, "wt": time.time(),
                                "ver": d.get("ver"), "rows": rows},
                               ensure_ascii=False) + "\n")
            f.flush()
            time.sleep(every)
    print(f"폴 {n}회(실패 {err}) → {out_path}")
    return 0


def pool(paths: list, max_age: int = MAX_AGE) -> int:
    """모은 스냅샷을 **도착 열쇠로 접어** 하루 건수를 직접 센다.

    ★대리 지표(비율 × 도착 38건)를 안 쓴다 — 도착을 세었으니 그냥 센다.
    ⚠덮이지 않은 시간대는 빠진다. 아래 «덮은 시간» 으로 먼저 확인할 것.
    ★날 가르기는 **벽시계 `wt`** 로 한다 — 행의 나이는 책의 `T` 로 이미 재어 두었고,
      `T` 는 «자정 이후 초» 라 날짜를 모른다. 두 축을 섞지 않는다.
    """
    seen: dict = {}
    polls: list = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    o = json.loads(line)
                except Exception:                              # noqa: BLE001
                    continue
                if o.get("ev") != "poll" or o.get("wt") is None:
                    continue
                polls.append(o["wt"])
                for r in o.get("rows") or []:
                    a = r.get("age")
                    if a is None or a > max_age or a < 0:
                        continue          # 알람은 «방금 온 것» 만 본다
                    k = r["key"]
                    if k not in seen or r["dev"] > seen[k]["dev"]:
                        seen[k] = r       # 같은 도착이면 가장 싸게 보인 순간으로
    if not polls:
        print("폴이 없다 — --sample 로 먼저 모은다")
        return 1
    days = collections.Counter(dt.date.fromtimestamp(t) for t in polls)
    print(f"폴 {len(polls)}회 · 날 {len(days)}개 · 나이 창 {max_age}초 안 도착 {len(seen)}건")
    for day, c in sorted(days.items()):
        ts = [t for t in polls if dt.date.fromtimestamp(t) == day]
        print(f"  {day}  폴 {c:5d}회  덮은 시간 "
              f"{dt.datetime.fromtimestamp(min(ts)):%H:%M}~"
              f"{dt.datetime.fromtimestamp(max(ts)):%H:%M}")
    nd = len(days)
    recs = list(seen.values())
    print(f"\n  {'문턱':>8s} {'도착 중 넘은 것':>16s} {'하루':>8s}   {'단가 병행 문턱':>14s}")
    for N in (1, 2, 3, 5, 7, 10):
        hit = [r for r in recs if r["dev"] >= N]
        w1 = [r for r in hit if (to_won(r["dev"], r["ttm"]) or 0) >= 1]
        w3 = [r for r in hit if (to_won(r["dev"], r["ttm"]) or 0) >= 3]
        print(f"  +{N:2d}bp  {len(hit):6d}/{len(recs):<6d} "
              f"({len(hit)/max(len(recs),1):5.1%}) {len(hit)/nd:6.1f}건   "
              f">=1원 {len(w1)/nd:5.1f}건 · >=3원 {len(w3)/nd:5.1f}건")
    _ttm_table(recs)
    print("\n  ★하루 건수는 **직접 센 것**이다(도착 열쇠로 접음) — 대리 지표가 아니다.")
    return 0


def main(argv: list) -> int:
    if "--port" in argv:
        use_port(int(argv[argv.index("--port") + 1]))
    if "--calibrate" in argv:
        return calibrate()
    if "--watch" in argv:
        i = argv.index("--watch")
        return watch(int(argv[i + 1]), argv[i + 2] if len(argv) > i + 2 else "alarm_watch.jsonl")
    if "--sample" in argv:
        i = argv.index("--sample")
        every = int(argv[i + 3]) if len(argv) > i + 3 else 20
        return sample(int(argv[i + 1]),
                      argv[i + 2] if len(argv) > i + 2 else "alarm_sample.jsonl", every)
    if "--pool" in argv:
        i = argv.index("--pool")
        return pool(argv[i + 1:] or ["alarm_sample.jsonl"])
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
