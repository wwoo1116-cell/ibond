# -*- coding: utf-8 -*-
"""v4 검증 — 서빙 중인 책을 «원본 로그» 와 대조한다.

교훈(2026-09-02): 「잘 도는 것처럼 보인다」와 「원본과 대조했다」는 다르다.
그때 화면은 멀쩡했는데 그날 최활발 종목이 통째로 빠져 있었다.

대조 대상(모두 v4 에서 새로 만든 것):
  A. 구조화 체결 테이프 — 원문의 CONFIRM 과 건수·방향·수익률·수량이 맞는가
  B. 국민주택 레인 — 은어/회차 칸 배정과 복원값이 문면과 맞는가
  C. 사다리 불변식 — 오퍼 금리 < 비드 금리, 크로스 없음(전 종목)

실행:  python verify_v4.py [--port 8302] [--at 11:00:00] [--day 20260902]
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from parse_kbond_logs import ROOMS, SRC_DIR, extract, split_messages   # noqa: E402
from enrich_kbond_quotes import restore, norm_code                     # noqa: E402
import kbond_live as KL                                                # noqa: E402
import kbond_issuer                                                    # noqa: E402

NHB_ORDER = KL.NHB_ORDER


def argv_get(flag, default):
    a = sys.argv[1:]
    return a[a.index(flag) + 1] if flag in a else default


def main() -> int:
    port = argv_get("--port", "8302")
    day = argv_get("--day", "20260902")
    at = argv_get("--at", "11:00:00")
    h, m, s = (at + ":0:0").split(":")[:3]
    T = int(h) * 3600 + int(m) * 60 + int(s)

    with urllib.request.urlopen(f"http://127.0.0.1:{port}/book.json", timeout=20) as r:
        book = json.load(r)
    fails = []
    strict = bool(book.get("replay"))
    if not strict:
        # 라이브는 시계가 계속 흐른다 — 책이 스스로 말하는 시각을 기준으로 잡고,
        # 건수 일치는 «참고» 로 낮춘다(스냅샷과 로그 읽기 사이에 메시지가 들어온다).
        at = book["now"]
        h, m, s2 = at.split(":")
        T = int(h) * 3600 + int(m) * 60 + int(s2)
    import re as _re
    _labs = [d.get("d") for d in (book.get("dealers") or [])[:20] if d.get("d")]
    masked = bool(_labs) and all(_re.fullmatch(r"H\d+-\d+", x) for x in _labs)
    print(f"책 시각 {book['now']} · 검증 기준 {at} · "
          f"리플레이 {book.get('replay')} · 엄격 {strict} · 가림 {masked}")
    if strict:
        assert book["now"] == at, f"책 시계({book['now']})가 검증 기준과 다릅니다"

    def note(msg):
        """엄격 모드에서는 실패, 라이브에서는 참고."""
        if strict and not masked:
            fails.append(msg)
        else:
            print("    (참고) " + msg)

    def note_masked(msg):
        """가림 모드에서는 원문(raw)·딜러 이름이 라벨로 바뀌어 있어 문자열 대조가
        서지 않는다. 그 대조는 `--no-mask` 리플레이가 맡고, 여기서는 참고로 남긴다."""
        if masked:
            print("    (가림) " + msg)
        else:
            fails.append(msg)

    # 원본을 독립적으로 다시 읽는다 (라이브 서버의 코드 경로를 쓰지 않는다)
    msgs = []
    for room in ROOMS:
        for p in sorted(Path(SRC_DIR).glob(f"채권_{room}_{day}_*.txt")):
            txt = p.read_text(encoding="cp949", errors="replace")
            for sender, tm, body in split_messages(txt):
                t = KL.tsec(tm)
                if t is None or t > T:
                    continue
                msgs.append((t, room, sender, tm, body, extract(body, day)))
    msgs.sort(key=lambda r: r[0])
    n_raw = len(msgs)
    # 서버와 같은 규칙으로 «방을 가로지르는 20초 안 같은 문구» 를 뺀다.
    # (규칙 자체를 여기서 다시 구현해 서버가 그대로 지키는지 본다)
    seen, kept, n_dup = {}, [], 0
    for r in msgs:
        t, room, sender, tm, body, d = r
        k = body.strip()
        prev = seen.get(k)
        seen[k] = (t, room)
        if prev and prev[1] != room and 0 <= t - prev[0] <= KL.DUP_WIN:
            n_dup += 1
            continue
        kept.append(r)
    msgs = kept
    # ★v8.1 다리 분할 — 서버 _feed_inner 와 같은 규칙으로 다리를 만든다.
    #   교체(국고 코드 둘)는 통째. 다리 extract 가 OTHER·방향 없음이면 버린다(꼬리).
    # ★서버와 «같은 한 벌»(kbond_live.message_legs)을 쓴다. 따로 구현하면 검증기가
    #   자기 구현을 검증하게 된다. 규칙 자체의 검정은 [D]·[F] 의 원문 대조가 한다.
    rows_all = []          # (t, room, sender, tm, 다리본문, 다리 d, 원문)
    n_split = 0
    for t, room, sender, tm, body, d in msgs:
        legs = KL.message_legs(body, day, d)
        if len(legs) > 1:
            n_split += 1
        for text, dl in legs:
            rows_all.append((t, room, sender, tm, text, dl, body))
    print(f"원본 메시지 {n_raw:,}건 (~{at}) · 방 중복 {n_dup:,}건 제외 → {len(msgs):,}건 "
          f"· 다리 분할 {n_split}건 → 행 {len(rows_all):,}")
    if book.get("n_dup") is not None and book["n_dup"] != n_dup:
        note(f"E1 중복 제외 수가 다름: 책 {book['n_dup']} != 재현 {n_dup}")
    if book["n_msg"] != n_raw:
        note(f"E2 원본 메시지 수가 다름: 책 {book['n_msg']} != 재현 {n_raw}")

    # ── A. 구조화 체결 ────────────────────────────────────────────────
    conf = [r[:6] for r in rows_all if r[5]["MsgType"] == "CONFIRM"]
    tape = book["tape"]
    n_ack = book["n_ack"]
    print(f"\n[A] 체결 — 원본 CONFIRM {len(conf)}건 · 테이프 {len(tape)}건 "
          f"+ 내용없음 {n_ack}건 = {len(tape) + n_ack}")
    if len(tape) + n_ack != len(conf):
        note(f"A1 CONFIRM 합이 안 맞음: {len(tape)}+{n_ack} != {len(conf)}")

    by_raw = {}
    for e in tape:
        by_raw.setdefault((e["t"], e["raw"][:60]), []).append(e)
    checked = miss = 0
    for t, room, sender, tm, body, d in conf:
        key = (t, body[:60])
        got = by_raw.get(key)
        if not got:
            continue
        e = got[0]
        checked += 1
        want_side = ("B" if d["Position"] == "BUY" else
                     "S" if d["Position"] == "SELL" else None)
        # ★v8: 귀속된 체결은 방향을 «그 호가» 에서 물려받는다(문면에 방향이 없을 때만)
        if e["s"] != want_side and not (
                want_side is None and e.get("csrc") in ("level", "prev")):
            fails.append(f"A2 방향 불일치 {tm} {body[:40]} : {e['s']} != {want_side}")
        # ★v7: 화면 수량은 AmountEff(기본단위 100억 반영)다.
        #   체결은 «직전 그 브로커 호가에서 상속» 될 수 있다 — 그때는 파서값과 다르다.
        #   상속이 «표기된 수량» 을 덮지는 않는지만 본다.
        if e.get("asrc") == "inherit":
            if d["AmountSource"] not in (None, "default"):
                fails.append(f"A3b 상속이 표기 수량을 덮음 {tm} {body[:40]}")
        elif e["a"] != d["AmountEff"]:
            fails.append(f"A3 수량 불일치 {tm} {body[:40]} : {e['a']} != {d['AmountEff']}")
        # 국고 체결은 민평 복원값과 대조
        if d["Sector"] == "국고" and d["BondCode"] and e["y"] is not None:
            mp = book["mp"].get(d["BondCode"])
            if mp is not None and d["QuoteRaw"] is not None:
                arr, _ = restore(pd.Series([d["QuoteRaw"]]), pd.Series([float(mp)]))
                want = None if pd.isna(arr[0]) else round(float(arr[0]), 3)
                if want is not None and abs(want - e["y"]) > 1e-9:
                    fails.append(f"A4 수익률 불일치 {tm} {body[:40]} : "
                                 f"{e['y']} != {want}")
    miss = len(tape) - checked
    print(f"    테이프 {len(tape)}건 중 원문 대조 {checked}건 · 못 찾음 {miss}건"
          + (" (가림 — 원문이 라벨로 바뀌어 문자열로 못 맞춘다)" if masked else ""))
    if miss and not masked:
        note(f"A5 테이프 {miss}건을 원문에서 못 찾음")

    # ── B. 국민주택 ───────────────────────────────────────────────────
    # ★«민평에» 행은 AXE 지만 책에 들어온다 [OWNER 2026-09-03]
    nhb_src = [r[:6] for r in rows_all
               if r[5]["Sector"] == "국민주택"
               and (r[5]["MsgType"] == "QUOTE" or r[5]["AtMP"])
               and r[5]["Position"] in ("BUY", "SELL")]
    # 같은 (딜러, 방향, 칸) 은 절대값 교체 -> 마지막 하나만 남는다
    want = {}
    ref_max = None
    per_rung_mp = {}
    for t, room, sender, tm, body, d in nhb_src:
        rung = None
        for w in NHB_ORDER:
            if w in body:
                rung = w
                break
        if rung is None:
            rung = ("국주 " + norm_code(pd.Series([str(d["SeriesNo"])]))[0]
                    ) if d["SeriesNo"] else (
                ("국주 " + str(d["Maturity"])) if d["Maturity"] else None)
        if rung is None:
            continue
        if d["MPYield"] is not None:
            per_rung_mp[rung] = round(float(d["MPYield"]), 3)
            if ref_max is None or d["MPYield"] > ref_max:
                ref_max = round(float(d["MPYield"]), 3)
        brk = d["BrokerKey"] or d["Broker"] or sender
        want[(brk, d["Position"], rung)] = (t, d, body, rung)
    got = {(e["d"], e["s"], e["code"]): e for e in book["nhb"]}
    print(f"\n[B] 국민주택 — 원본 호가 {len(nhb_src)}건 · 교체 후 {len(want)}칸 · "
          f"책 {len(book['nhb'])}칸 · 기준 민평 {book['nhb_ref']}")
    if len(want) != len(book["nhb"]):
        note(f"B1 칸 수 불일치: 원본 {len(want)} != 책 {len(book['nhb'])}")
    if book["nhb_ref"] != ref_max:
        fails.append(f"B2 기준 민평 불일치: {book['nhb_ref']} != {ref_max}")
    # 값 대조: 표시명이 아니라 (방향, 칸, 시각, 복원값) 으로 맞춘다
    idx = {(e["s"], e["code"], e["t"]): e for e in book["nhb"]}
    okv = 0
    for (brk, pos, rung), (t, d, body, _r) in want.items():
        e = idx.get(("B" if pos == "BUY" else "S", rung, t))
        if e is None:
            note(f"B3 책에 없음: {rung} {pos} {t} :: {body[:40]}")
            continue
        ref = per_rung_mp.get(rung, ref_max)
        exp = None
        if d["AtMP"]:
            exp = round(float(ref), 3) if ref is not None else None
        if exp is None and d["QuoteRaw"] is not None and ref is not None:
            arr, _ = restore(pd.Series([d["QuoteRaw"]]), pd.Series([float(ref)]))
            exp = None if pd.isna(arr[0]) else round(float(arr[0]), 3)
        if exp is None and d["AbsYield"] is not None:
            exp = round(float(d["AbsYield"]), 3)
        # ★[OWNER 2026-09-07] 국주도 «문면 민평만 적고 팔자» 꼴이 있다 —
        #   그 경우 레벨은 그 메시지가 적은 민평 그 자리다(책과 같은 규칙).
        if (exp is None and d["MPYield"] is not None and d["MsgType"] == "QUOTE"
                and d["QuoteRaw"] is None and d["SpreadValue"] is None
                and not d["IsInquiry"]):
            exp = round(float(d["MPYield"]), 3)
        if (e["y"] is None) != (exp is None) or (
                e["y"] is not None and abs(e["y"] - exp) > 1e-9):
            fails.append(f"B4 복원값 불일치 {rung} {t} :: {body[:40]} : "
                         f"{e['y']} != {exp}")
        else:
            okv += 1
    print(f"    복원값 대조 {okv}/{len(want)}")

    # ── C2. «민평에» 규칙 ─────────────────────────────────────────────
    #   레벨 없는 호가는 민평에 한다 [OWNER 2026-09-03]. 책의 atmp 행은
    #   y 가 정확히 그 종목의 민평이어야 한다(만들어 낸 값이 아니어야 한다).
    n_at = bad_at = 0
    for e in book["ktb"]:
        if not e.get("atmp"):
            continue
        n_at += 1
        m = book["mp"].get(e["code"])
        if m is None or abs(float(m) - e["y"]) > 1e-9:
            fails.append(f"C2 민평에 행의 레벨이 민평이 아님 {e['code']}: {e['y']} != {m}")
            bad_at += 1
    for e in book["msb"]:
        if not e.get("atmp"):
            continue
        n_at += 1
        m = (book.get("msb_mp") or {}).get(e["code"])
        if m is None or abs(float(m) - e["y"]) > 1e-9:
            fails.append(f"C2 통안 민평에 행 {e['code']}: {e['y']} != {m}")
            bad_at += 1
    print()
    print(f"[C2] «민평에» 행 {n_at}건 — 레벨이 그 종목 민평과 일치 {n_at - bad_at}/{n_at}")

    # ── C. 사다리 불변식 ──────────────────────────────────────────────
    def uncross(rows):
        asks = [e for e in rows if e["s"] == "S"]
        bids = [e for e in rows if e["s"] == "B"]
        for _ in range(200):
            if not asks or not bids:
                break
            ba = max(asks, key=lambda e: (e["y"], e["t"]))
            bb = min(bids, key=lambda e: (e["y"], -e["t"]))
            if ba["y"] < bb["y"]:
                break
            if ba["t"] <= bb["t"]:
                asks = [e for e in asks if e is not ba]
            else:
                bids = [e for e in bids if e is not bb]
        return asks, bids

    n_lad = 0
    for lane, ttl in (("ktb", 1800), ("msb", 1800), ("nhb", 1800)):
        src = [e for e in book[lane]
               if e.get("y") is not None and T - e["t"] <= ttl]
        codes = {e["code"] for e in src}
        for c in codes:
            a, b = uncross([e for e in src if e["code"] == c])
            if not a or not b:
                continue
            n_lad += 1
            fa = max(a, key=lambda e: (e["y"], e["t"]))
            fb = min(b, key=lambda e: (e["y"], -e["t"]))
            if not (fa["y"] < fb["y"]):
                fails.append(f"C1 크로스 잔존 {lane} {c}: 오퍼 {fa['y']} >= 비드 {fb['y']}")
    print(f"\n[C] 양면 사다리 {n_lad}종 — 오퍼 금리 < 비드 금리 · 크로스 없음")

    # ── D. 메시지 피드 ────────────────────────────────────────────────
    feed = book.get("feed") or []
    n_seq = book.get("n_seq", 0)
    print()
    print(f"[D] 피드 — 적재 {n_seq} (= 오늘 {book['n_msg']} − 중복 "
          f"{book.get('n_dup', 0)}) · 꼬리 {len(feed)}건")
    want_seq = len(rows_all)
    if n_seq != want_seq:
        note(f"D1 일련번호가 «적재분(다리 행)» 과 다름: {n_seq} != {want_seq} "
             f"(메시지 {book['n_msg']}-중복 {book.get('n_dup', 0)}={book['n_msg'] - book.get('n_dup', 0)})")
    # ★순서로 맞추면 안 된다. 같은 초에 두 방으로 같은 문구가 들어가고(중개사가 양쪽에
    #   뿌린다), 라이브 서버는 폴링 주기마다 방 단위로 먹여서 초 안의 순서가 다르다.
    #   그래서 (시각, 방, 원문) 을 열쇠로 «집합» 대조한다.
    from collections import defaultdict
    idx = defaultdict(list)
    for t, room, sender, tm, body, d, raw in rows_all:
        # 가림이면 책의 raw 가 서명 자리를 라벨로 바꾼 것이라 원문과 다르다.
        # 그때는 (시각, 방) + «서명을 뗀 앞부분» 으로 맞춘다.
        k_raw = (KL.split_broker(raw)[1][:60] if masked else raw[:170])
        idx[(t, room, k_raw)].append((tm, d, body))
    # /feed.json 백필도 같은 잣대로 본다 (새로고침 뒤 스크롤백의 출처다)
    import urllib.request as _u
    with _u.urlopen(f"http://127.0.0.1:{port}/feed.json?limit=3000", timeout=30) as r:
        back = json.load(r)
    bf = back.get("feed") or []
    bad_i = sum(1 for a, b in zip(bf, bf[1:]) if b["i"] <= a["i"])
    print(f"    백필 /feed.json {len(bf)}건 · i 오름차순 어긋남 {bad_i} · "
          f"서버 최대 i {back.get('n_seq')}")
    if bad_i:
        fails.append(f"D8 백필 i 순서 어긋남 {bad_i}건")
    if bf and any(e["i"] > back.get("n_seq", 0) for e in bf):
        fails.append("D9 백필에 n_seq 를 넘는 i 가 있음")
    feed = bf + [e for e in feed if not bf or e["i"] > bf[-1]["i"]]

    okd = unmatched = 0
    for e in feed:
        key = (e["t"], e["r"],
               (KL.split_broker(e["raw"])[1][:60] if masked else e["raw"]))
        cands = idx.get(key)
        if not cands:
            unmatched += 1
            continue
        pick = None
        why = None
        for j, (tm, d, body) in enumerate(cands):
            if e["k"] != d["MsgType"]:
                why = why or f"D4 종류 {e['k']} != {d['MsgType']}"
                continue
            want_side = ("B" if d["Position"] == "BUY" else
                         "S" if d["Position"] == "SELL" else None)
            if d["Position"] == "SWAP" and d["MsgType"] in ("QUOTE", "AXE"):
                # 교체 행의 «방향» 은 면이다 — 신형을 사면 비드, 팔면 오퍼.
                _b, _s = KL.swap_legs(body)
                if _b is not None:
                    _new = KL.swap_newer(_b, _s)
                    want_side = "B" if _b == _new else "S"
            if e["s"] != want_side and not (
                    want_side is None and e.get("csrc") in ("level", "prev")):
                why = why or f"D5 방향 {e['s']} != {want_side}"
                continue
            if e.get("asrc") == "inherit":
                if d["AmountSource"] not in (None, "default"):
                    why = why or f"D6c 상속이 표기 수량을 덮음"
                    continue
            else:
                if e["a"] != d["AmountEff"]:
                    why = why or f"D6 수량 {e['a']} != {d['AmountEff']}"
                    continue
                if e.get("asrc") != d["AmountSource"]:
                    why = why or f"D6b 수량 출처 {e.get('asrc')} != {d['AmountSource']}"
                    continue
            pick = j
            break
        if pick is None:
            tm, d, body = cands[0]
            fails.append(f"{why} {tm} :: {body[:40]}")
            cands.pop(0)
            continue
        cands.pop(pick)
        okd += 1
    print(("    (가림 — 원문 대조는 --no-mask 리플레이가 맡는다) " if masked else "")
          + f"    원본에서 찾아 대조 {okd}/{len(feed)}"
          + (f" · 원본에 없음 {unmatched}건" if unmatched else ""))
    if unmatched and not masked:
        note(f"D2 피드 {unmatched}건을 원본에서 못 찾음(스냅샷 이후 도착분 포함)")

    # ── E. 교체 책 · 내재 행 ───────────────────────────────────────────
    swap = book.get("swap") or []
    print()
    print(f"[E] 교체 — 책 {len(swap)}건")
    # 원본에서 같은 규칙으로 다시 뽑는다 (규칙 자체를 검정한다)
    want = {}
    n_swap_msg = n_legs = 0
    for t, room, sender, tm, body, d in msgs:
        if d["Position"] != "SWAP" or d["MsgType"] not in ("QUOTE", "AXE"):
            continue
        n_swap_msg += 1
        buy, sell = KL.swap_legs(body)
        if buy is None:
            continue
        n_legs += 1
        new = KL.swap_newer(buy, sell)
        old = sell if new == buy else buy
        face = "B" if buy == new else "S"
        lvl = (float(d["SpreadValue"])
               if d["SpreadSource"] == "swap" and d["SpreadUnit"] == "bp" else None)
        brk = d["BrokerKey"] or d["Broker"] or sender
        want[(str(brk)[:14], face, f"{old}/{new}")] = (tm, lvl, d["AmountEff"],
                                                       d["AmountSource"], body)
    print(f"    원본 교체 메시지 {n_swap_msg}건 · 두 다리 확정 {n_legs}건 "
          f"· 교체 후 {len(want)}칸")
    got = {(e["k"], e["s"], e["pair"]): e for e in swap}
    okE = 0
    for k, (tm, lvl, amt, asrc, body) in want.items():
        e = got.get(k)
        if e is None:
            # 가림이면 브로커키가 라벨(K001)이라 키로 못 찾는다 — 면·쌍만 본다
            if masked:
                if not any(x["s"] == k[1] and x["pair"] == k[2] for x in swap):
                    note_masked(f"E1 책에 없음: {k} :: {body[:40]}")
                continue
            note(f"E1 책에 없음: {k} :: {body[:40]}")
            continue
        if masked:
            okE += 1
            continue
        if e["y"] != lvl:
            fails.append(f"E2 레벨 불일치 {tm} {k}: {e['y']} != {lvl}")
            continue
        if e["a"] != amt or e.get("asrc") != asrc:
            fails.append(f"E3 수량 불일치 {tm} {k}: {e['a']}/{e.get('asrc')} "
                         f"!= {amt}/{asrc}")
            continue
        okE += 1
    print(f"    원문 대조 {okE}/{len(want)}")
    if len(got) != len(want):
        note(f"E4 칸 수 다름: 책 {len(got)} != 재현 {len(want)}")

    # 쌍마다 오퍼 < 비드 (교체 축에서도 같은 불변식)
    from collections import defaultdict as _dd
    byp = _dd(list)
    for e in swap:
        if e["y"] is not None and T - e["t"] <= 1800:
            byp[e["pair"]].append(e)
    n_pair = 0
    for pair, es in byp.items():
        a, b = KL.uncross_best(es)
        if a is None or b is None:
            continue
        n_pair += 1
        if not (a["y"] < b["y"]):
            fails.append(f"E5 교체 크로스 {pair}: 오퍼 {a['y']} >= 비드 {b['y']}")
    print(f"    양면 쌍 {n_pair} — 오퍼 < 비드 · 크로스 없음")

    # 내재 행: 실호가와 크로스 0 · 내재끼리 크로스 0
    imp = book.get("implied") or {}
    n_imp = sum(len(v) for v in imp.values())
    for code, rows in imp.items():
        real = [e for e in book["ktb"] if e["code"] == code
                and e.get("y") is not None and T - e["t"] <= 1800]
        ra, rb = KL.uncross_best(real)
        for r in rows:
            if r["s"] == "S" and rb is not None and r["y"] >= rb["y"]:
                fails.append(f"E6 내재오퍼가 실비드와 크로스 {code}: {r['y']} >= {rb['y']}")
            if r["s"] == "B" and ra is not None and r["y"] <= ra["y"]:
                fails.append(f"E7 내재비드가 실오퍼와 크로스 {code}: {r['y']} <= {ra['y']}")
        ia = max((r for r in rows if r["s"] == "S"), key=lambda r: r["y"], default=None)
        ib = min((r for r in rows if r["s"] == "B"), key=lambda r: r["y"], default=None)
        if ia and ib and ia["y"] >= ib["y"]:
            fails.append(f"E8 내재끼리 크로스 {code}: {ia['y']} >= {ib['y']}")
    print(f"    내재 행 {n_imp}건 ({len(imp)}종) — 실호가·내재 크로스 0")

    # ── F. 체결 귀속 [v8] ─────────────────────────────────────────────
    #   귀속 행마다 «같은 딜러의 호가가 그 창 안에 실제로 있었는지» 를 원문에서
    #   다시 찾는다. level 은 QuoteRaw 까지 같아야 하고, 국고면 종목도 같아야 한다.
    print()
    inf = [e for e in tape if e.get("csrc") in ("level", "prev")]
    win = book.get("fill_win") or {"level": 1800, "prev": 60}
    cnt = {"level": 0, "prev": 0}
    for e in inf:
        cnt[e["csrc"]] += 1
    fi = book.get("fill_inf") or {}
    print(f"[F] 체결 귀속 — 테이프 {len(tape)}건 중 귀속 {len(inf)}건 "
          f"(level {cnt['level']} · prev {cnt['prev']}) · "
          f"서버 집계 {fi}")
    for kk in cnt:
        if fi.get(kk) != cnt[kk]:
            note(f"F1 귀속 집계 불일치 {kk}: 서버 {fi.get(kk)} != 테이프 {cnt[kk]}")
    # 원문에서 «딜러 표시명 -> 호가 목록» (서버 코드 경로가 아니라 파서 결과로)
    # ★모든 호가류 메시지(교체·못 실은 것 포함)가 후보다 — 서버는 못 실은 호가를
    #   차단자로 남겨서, 딜러의 마지막 호가가 그것이면 귀속하지 않는다.
    qlog = {}
    for t, room, sender, tm, body, d, raw in rows_all:
        if d["Position"] not in ("BUY", "SELL", "SWAP"):
            continue
        if not (d["MsgType"] == "QUOTE" or (d["MsgType"] == "AXE" and d["AtMP"])):
            continue
        # 열쇠는 서버와 같은 브로커키(표시명이 같아도 데스크가 다를 수 있다)
        brk = str(d["BrokerKey"] or d["Broker"] or sender)[:14]
        # 서버와 같은 규약: 코드 없는 «국딱» 은 그날 입찰물이다
        if (d["Sector"] == "국고" and not d["BondCode"] and "국딱" in body
                and (book.get("auction") or {}).get("bc")):
            d = dict(d, BondCode=book["auction"]["bc"])
        qlog.setdefault(brk, []).append((t, d))
    okF = 0
    if masked:
        print("    (가림 모드 — 딜러 라벨은 서버와 번호가 다를 수 있어 원문 대조를 건너뛴다."
              " 리플레이는 --no-mask 로 검증한다)")
        inf = []
    for e in inf:
        cands = [(t, d) for (t, d) in qlog.get(e.get("k") or e["d"], []) if t <= e["t"]]
        lo = e["t"] - win[e["csrc"]]
        cands = [(t, d) for (t, d) in cands if t >= lo]
        if e["csrc"] == "level":
            # 레벨이 적힌 체결 -> 같은 QuoteRaw(또는 절대금리) 를 가진 호가
            raw = next((dd for (_tm, dd, _b) in idx.get(
                (e["t"], e["room"], e["raw"][:170]), []) if dd is not None), None)
            cands2 = cands
            if raw is not None and raw["QuoteRaw"] is not None:
                cands2 = [(t, d) for (t, d) in cands if d["QuoteRaw"] == raw["QuoteRaw"]]
            if e["lane"] == "ktb":
                cands2 = [(t, d) for (t, d) in cands2 if d["BondCode"] == e["code"]]
            if not cands2:
                fails.append(f"F2 level 귀속인데 같은 딜러·같은 레벨 호가가 창 안에 없음 "
                             f"{e['t']} {e['d']} {e['code']} :: {e['raw'][:40]}")
                continue
        else:
            if not cands:
                fails.append(f"F3 {e['csrc']} 귀속인데 같은 딜러 호가가 "
                             f"{win[e['csrc']]}초 안에 없음 {e['t']} {e['d']} :: {e['raw'][:40]}")
                continue
            last = max(cands, key=lambda x: x[0])
            want_sec = {"ktb": "국고", "msb": "통안", "nhb": "국민주택",
                        "cr": "크레딧/기타"}.get(e["lane"])
            if last[1]["Sector"] != want_sec or last[1]["Position"] == "SWAP":
                fails.append(f"F4b 직전 호가 레인이 다름 {e['t']} {e['d']}: "
                             f"{e['lane']} != {last[1]['Sector']}/{last[1]['Position']}")
                continue
            if e["lane"] == "ktb" and last[1]["BondCode"] != e["code"]:
                fails.append(f"F4 직전 호가 종목과 다름 {e['t']} {e['d']}: "
                             f"{e['code']} != {last[1]['BondCode']}")
                continue
        okF += 1
    print(f"    원문 대조 {okF}/{len(inf)}")

    # ── F2. 끝전 환산 [PROMPT_frac [4]c] ──────────────────────────────
    #   Q 행: 우리 환산이 딜러의 결과금리와 맞는가(본표 실측 |중앙| 0.09bp · p90 0.79bp).
    #   C·E 행: 만들어 낸 값이 민평 근처에 있는가. N 행: 값이 없는가.
    cr = book.get("credit") or []
    won = [e for e in cr if e.get("unit") == "원"]
    byl = {}
    for e in won:
        byl.setdefault(e.get("lvl"), []).append(e)
    print()
    print(f"[F2] 끝전 — 크레딧 원 행 {len(won)}건 · "
          + " · ".join(f"{k or 'N(미상)'} {len(v)}" for k, v in sorted(
              byl.items(), key=lambda kv: str(kv[0]))))
    chk = [e["chk"] for e in byl.get("quoted", []) if e.get("chk") is not None]
    if chk:
        ok1 = sum(1 for v in chk if abs(v) <= 1.0)
        srt = sorted(abs(v) for v in chk)
        print(f"     Q 대사 {len(chk)}건 · |chk| ≤ 1bp {100 * ok1 / len(chk):.1f}% "
              f"· |중앙| {srt[len(srt) // 2]:.2f}bp · p90 {srt[int(len(srt) * .9)]:.2f}bp")
        if ok1 / len(chk) < 0.85:
            fails.append(f"F2a 끝전 환산이 문면 결과금리와 어긋남: "
                         f"|chk| ≤ 1bp {100 * ok1 / len(chk):.1f}% < 85%")
            for e in sorted(byl["quoted"], key=lambda x: -abs(x.get("chk") or 0))[:5]:
                if e.get("chk") is not None and abs(e["chk"]) > 1.0:
                    fails.append(f"     {e['n']} chk {e['chk']}bp · 끝전 {e.get('frac')} "
                                 f"· 원 {e.get('won')} · 잔존 {e.get('ttm')}")
    for lv in ("conv", "est"):
        for e in byl.get(lv, []):
            if e.get("ytm") is None or e.get("mp") is None:
                fails.append(f"F2b {lv} 인데 값이 없음: {e['n']}")
            elif abs(e["ytm"] - e["mp"]) * 100 > 30:
                fails.append(f"F2c {lv} 가 민평에서 30bp 넘게 떨어짐: {e['n']} "
                             f"{e['ytm']} vs 민평 {e['mp']} · 원 {e.get('won')} "
                             f"· 끝전 {e.get('frac')} · 잔존 {e.get('ttm')}")
        n_bad_src = sum(1 for e in byl.get(lv, [])
                        if (e.get("fsrc") == "assumed") != (lv == "est"))
        if n_bad_src:
            fails.append(f"F2d {lv} 의 끝전 출처가 어긋남 {n_bad_src}건")
    for e in byl.get(None, []):
        if e.get("ytm") is not None or e.get("dbp") is not None:
            fails.append(f"F2e 레벨 미상인데 값이 있음: {e['n']} ytm={e.get('ytm')}")
    n_est_short = sum(1 for e in byl.get("est", [])
                      if e.get("ttm") is not None and e["ttm"] < KL.FRAC_EST_MIN_TTM)
    if n_est_short:
        fails.append(f"F2f 잔존 {KL.FRAC_EST_MIN_TTM}년 미만인데 0.5 가정 {n_est_short}건")
    print(f"     C·E 값 범위 · N 무값 · 추정 문턱 {KL.FRAC_EST_MIN_TTM}년 확인")

    # ── G. 맥박 · 딜러 · 이벤트 [v8] ──────────────────────────────────
    pulse = book.get("pulse") or {}
    tot = sum(v["q"] + v["a"] + v["c"] + v["i"] + v["o"] for v in pulse.values())
    print()
    print(f"[G] 맥박 {len(pulse)}버킷 합 {tot} (= 적재 {n_seq}) · "
          f"딜러 {len(book.get('dealers') or [])}곳 · 이벤트 {book.get('n_event')}")
    if tot != n_seq:
        note(f"G1 맥박 합이 적재분과 다름: {tot} != {n_seq}")
    # 딜러 상위 10 의 건수를 원문(브로커키)에서 다시 센다
    from collections import Counter
    cnt_k = Counter()
    for t, room, sender, tm, body, d, raw in rows_all:
        cnt_k[str(d["BrokerKey"] or d["Broker"] or sender)[:14]] += 1
    badG = 0
    if masked:
        # 라벨 번호는 못 맞춘다 — 상위 10 «건수» 가 원문 상위 10 과 같은 다중집합인가
        want = sorted((v for _, v in cnt_k.most_common(10)), reverse=True)
        got = sorted((d["n"] for d in (book.get("dealers") or [])[:10]), reverse=True)
        if want != got:
            badG = 1
            note(f"G2 상위 10 딜러 건수 분포가 다름: 책 {got} != 원문 {want}")
        print(f"    상위 10 딜러 건수 분포 {'일치' if not badG else '불일치'} (가림 모드)")
    else:
        for ds in (book.get("dealers") or [])[:10]:
            if cnt_k.get(ds["k"]) != ds["n"]:
                badG += 1
                note(f"G2 딜러 건수 불일치 {ds['k']}: 책 {ds['n']} != 원문 {cnt_k.get(ds['k'])}")
        print(f"    상위 10 딜러 건수 원문 일치 {10 - badG}/10")
    ev = book.get("events") or []
    nf_ev = sum(1 for x in ev if x["k"] == "fill")
    nf_tp = sum(1 for e in tape if e.get("code")
                and e.get("lane") in ("ktb", "msb", "nhb"))
    if book.get("n_event", 0) <= 240 and nf_ev != nf_tp:
        note(f"G3 체결 이벤트 수 {nf_ev} != 테이프 귀속 체결 {nf_tp}")
    badX = 0
    for x in ev:
        if x["k"] == "cross" and x.get("x"):
            vs = x["x"]["vs"]
            # ★[OWNER] 락(간격 0)은 이벤트가 아니다 — 0.5bp 이상 «넘어선» 것만
            gap = (x["y"] - vs) if x["s"] == "S" else (vs - x["y"])
            if gap * 100 < KL.CROSS_MIN_BP - 1e-9:
                badX += 1
                fails.append(f"G4 크로스 이벤트 간격이 {gap*100:.2f}bp "
                             f"(< {KL.CROSS_MIN_BP}bp) {x}")
    print(f"    이벤트 {len(ev)}건 (체결 {nf_ev} · 크로스 {sum(1 for x in ev if x['k']=='cross')} "
          f"· 최우선 {sum(1 for x in ev if x['k']=='best')} · 대량 {sum(1 for x in ev if x['k']=='size')}"
          f" · 첫호가 {sum(1 for x in ev if x['k']=='first')}) · 크로스 조건 위반 {badX}")

    # ── H. 가림 [OWNER 2026-09-03 「딜러이름이랑 번호는 일단 XXX로」] ──
    #   책 어디에도 실명·전화가 남아 있으면 안 된다. 문자열 전체를 훑는다.
    print()
    if not masked:
        print("[H] 가림 꺼짐 — 딜러 실명·전화가 그대로 나간다(로컬 확인용)")
    else:
        # ★딜러가 실릴 수 있는 «자리» 만 본다. 책 전체를 훑으면 국고 정식표기
        #   (서명 XXXX-XXXX) 가 전화번호로, 발행사명(«아이엠캐피탈143-2») 이
        #   데스크명으로 잡힌다 — 둘 다 가릴 대상이 아니다(실측 오탐 46+1건).
        # ★자리마다 잣대가 다르다.
        #   spots  = 라벨이어야 하는 자리(d·bk·h·k·vd) — 데스크명이 조금이라도 있으면 누출.
        #   labels = 종목 이름 자리(n) — «완전 일치» 만. 발행사명 «아이엠캐피탈143-2» 는
        #            데스크명 «아이엠» 을 품지만 가릴 대상이 아니다.
        #   raws   = 원문 — 발행사명이 당연히 들어 있다. 여기서는 «전화번호» 만 본다.
        #            (서명은 split_broker 가 전화번호를 보고 떼므로, 전화번호가 0 이면
        #             서명도 떨어진 것이다. 전화번호 없는 서명은 파서도 브로커로 안 읽는다.)
        spots, labels, raws = [], set(), []
        for e in (book.get("feed") or []):
            spots += [e.get("d"), e.get("bk"), e.get("h")]
            raws.append(e.get("raw"))
            labels.add(e.get("n"))
        for e in (book.get("tape") or []):
            spots += [e.get("d"), e.get("k")]
            raws.append(e.get("raw"))
            labels.add(e.get("n"))
        for lane in ("ktb", "msb", "nhb", "credit", "swap", "baskets"):
            for e in (book.get(lane) or []):
                spots += [e.get("d"), e.get("k")]
                labels.add(e.get("n"))
        for e in (book.get("dealers") or []):
            spots += [e.get("d"), e.get("k")]
        for e in (book.get("events") or []):
            spots += [e.get("d"), (e.get("x") or {}).get("vd")]
            labels.add(e.get("n"))
        # ★종목 이름 자리(n)는 «완전 일치» 만 본다 — 발행사명 «아이엠캐피탈143-2» 는
        #   데스크명 «아이엠» 을 부분 문자열로 품지만 가릴 대상이 아니다(실측 오탐).
        blob = " || ".join(str(x) for x in spots if x)
        labels = {str(x) for x in labels if x}
        raw_blob = " || ".join(str(x) for x in raws if x)
        tel = set(_re.findall(r"(?<!\d)(?:0\d{1,2}[-.\s])?\d{3,4}[-.\s]\d{4}(?!\d)",
                              blob + " || " + raw_blob))
        names = set()
        for t, room, sender, tm, body, d, raw in rows_all:
            brk = d["BrokerKey"] or d["Broker"] or sender
            nm = KL._raw_disp(d, brk)
            if nm and len(nm) >= 3:
                names.add(nm)
        # ★[2026-09-09] 종목 이름 자리는 «데스크명과 완전 일치» 로 봤는데, 발행체를
        #   정본화한 뒤로 증권사가 **발행체이면서 동시에 데스크명** 인 자리가 생겼다
        #   (실측: n='신한투자증권' 회사채 AA0 오퍼 3.602 — 딜러는 H09-10 로 제대로
        #   가려져 있었다). 예전엔 라벨에 회차가 붙어 완전 일치가 안 났을 뿐이다.
        #   사전이 «발행체» 라고 아는 이름은 누출이 아니다. 원문(blob)은 그대로 본다.
        _iss_labels = {x for x in labels
                       if kbond_issuer.canon_issuer(x)[1] not in (None, "raw")}
        leaked = sorted(n for n in names if n in blob or n in (labels - _iss_labels))
        labs = {d.get("d") for d in (book.get("dealers") or [])}
        bad_lab = sorted(x for x in labs if x and not _re.fullmatch(r"H\d+-\d+", x))
        print(f"[H] 가림 — 딜러 라벨 {len(labs)}개 · 전화번호꼴 {len(tel)} · 실명 노출 {len(leaked)}")
        if tel:
            fails.append(f"H1 책에 전화번호꼴이 남아 있음 {len(tel)}건: {sorted(tel)[:5]}")
        if leaked:
            fails.append(f"H2 책에 데스크 실명이 남아 있음 {len(leaked)}건: {leaked[:5]}")
        if bad_lab:
            fails.append(f"H3 라벨 꼴이 아닌 딜러명 {len(bad_lab)}건: {bad_lab[:5]}")

    # ── [I] 체결 귀속의 공격 방향 (v12) ──────────────────
    # 귀속은 (딜러, 종목, 레벨) 셋만 쓴다 — 방향은 «안 쓴 축» 이라 검정이 된다.
    # 문면 방향 s 와 공격 방향 ag 는 서로 반대여야 한다(오퍼가 맞았으면 사 간 것).
    # 배치 실측 99.2% (n=24,778) — RESULT_fill_attribution_2026-09-07.md
    print()
    ags = [e for e in tape if e.get("ag") and e.get("s")]
    n_ag = sum(1 for e in tape if e.get("ag"))
    ok_ag = sum(1 for e in ags if e["s"] != e["ag"])
    rate = ok_ag / len(ags) * 100 if ags else 100.0
    print(f"[I] 체결 귀속 방향 — 테이프 {len(tape)}건 중 책에 붙은 것 {n_ag}건 · "
          f"문면 방향까지 있는 것 {len(ags)}건")
    print(f"    공격 방향이 문면과 맞음 {ok_ag}/{len(ags)} ({rate:.1f}%)"
          f"  [귀속에 안 쓴 축 — 양성대조군]")
    if ags and rate < 85.0:
        fails.append(f"I1 공격 방향 일치율 {rate:.1f}% < 85% — 귀속 규칙을 의심할 것")
    agg = book.get("aggr") or {}
    if sum(agg.values()) != n_ag:
        fails.append(f"I2 공격 방향 집계 불일치: 서버 {agg} 합 {sum(agg.values())}"
                     f" != 테이프 {n_ag}")
    else:
        print(f"    서버 집계 {agg} — 테이프와 일치")

    print("\n" + "=" * 60)
    if fails:
        print(f"실패 {len(fails)}건")
        for f in fails[:40]:
            print("  -", f)
        return 1
    print("전건 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
