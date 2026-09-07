# -*- coding: utf-8 -*-
"""화면이 쓸 값을 «서버에서» 계산한다. [OWNER 2026-09-03 「계산과 집계는 서버」]

## 왜 옮기는가

지금까지 서버는 원시 호가 목록을 통째로 보내고, 화면이 받을 때마다 활성 필터·무크로스·
최우선·중앙값·히트맵 칸을 다시 계산했다. 그래서

  - 스냅샷이 809KB 이고 갱신마다 통째로 간다,
  - 같은 규칙이 파이썬(검증기)과 자바스크립트(화면) 두 벌로 존재하고,
  - React 로 옮기면 그 두 벌을 «세 번째로» 베끼게 된다.

계산을 여기로 모으면 화면은 받은 것을 그리기만 한다.

## 규약 — 화면의 것과 한 글자도 다르면 안 된다

이 파일의 함수는 `kbond_live.html` 의 같은 이름 함수를 그대로 옮긴 것이다.
**옮기면서 «더 낫게» 고치지 않았다.** 다르면 대조가 깨지고, 그 순간 어느 쪽이 맞는지
아무도 모른다. 개선은 대조가 선 뒤에 양쪽을 같이 고쳐서 한다.
  - 무크로스: 크로스 쌍 중 «오래된» 쪽 제거 (uncross)
  - 최우선: 오퍼 = 오퍼 중 최고 금리, 비드 = 비드 중 최저 금리, 동률이면 최신 (best_of)
  - 활성: T - t <= TTL. 국고·통안·국주 1800초 · 크레딧 7200초
  - mid: 최우선 둘이 다 있을 때만. 없으면 hist 의 마지막 표본
  - 중앙값: 정렬 후 s[len//2] — 짝수에서 «위쪽» 을 고른다(JS 와 같게)

대조는 `test_view_parity.py` 가 «브라우저에서 뽑은 화면 계산» 과 여기 값을 맞대 본다.
"""
from __future__ import annotations

# 화면 상수와 같은 값 (kbond_live.html 의 CLSORD·RTORD·NHBORD·BUCKETS·HMROWS)
CLSORD = ["지방채", "공사채", "특은채", "은행채", "여전채", "회사채",
          "MBS", "국고이자채"]
RTORD = ["AAA", "AA+", "AA0", "AA-", "A+", "A0", "A-",
         "BBB+", "BBB0", "BBB-", "BBB", "미상"]
NHBORD = ["국당", "국전", "국전전", "국전당"]
BUCKETS = [(0, 1, "~1년"), (1, 2, "1~2"), (2, 3, "2~3"),
           (3, 5, "3~5"), (5, 10, "5~10"), (10, 99, "10년+")]
HMROWS = [("국고채", None), ("통안채", None), ("지방채", "AAA"), ("공사채", "AAA"),
          ("특은채", "AAA"), ("은행채", "AAA"), ("카드채", "AA+"),
          ("여전채", "AA-"), ("회사채", "AAA")]
# credit_matrix 의 bond_type — 종별 «대표 신용등급» [OWNER]
CB_BY_RT = {"AAA": "CB1", "AA+": "CB2", "AA0": "CB3", "AA": "CB3", "AA-": "CB4"}
MTX_BY_CLS = {"여전채": "OFB", "카드채": "CARD", "은행채": "BD",
              "특은채": "KDB", "공사채": "SPB"}


def ttl_for(kind, mode="def"):
    """화면의 ttlFor. 수명 토글은 «표시 필터» 이지 책을 바꾸지 않는다."""
    if mode == "inf":
        return float("inf")
    base = 7200 if kind == "credit" else 1800
    return base / 2 if mode == "half" else base


def alive(e, kind, T, mode="def"):
    return T - e["t"] <= ttl_for(kind, mode)


def uncross(rows):
    """크로스 쌍 중 «오래된» 쪽을 지운다. 화면 uncross 와 같은 순서로 돈다."""
    asks = [e for e in rows if e.get("s") == "S"]
    bids = [e for e in rows if e.get("s") == "B"]
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


def best_of(asks, bids):
    """최우선 (오퍼, 비드). 오퍼는 «가장 비싼 금리», 비드는 «가장 싼 금리», 동률이면 최신."""
    fa = max(asks, key=lambda e: (e["y"], e["t"])) if asks else None
    fb = min(bids, key=lambda e: (e["y"], -e["t"])) if bids else None
    return fa, fb


def med(a):
    """화면의 med — 정렬 뒤 s[len//2]. 짝수에서 «위쪽» 을 고르는 것까지 같다."""
    if not a:
        return None
    s = sorted(a)
    return s[len(s) // 2]


def bucket_of(y):
    for lo, hi, name in BUCKETS:
        if lo <= y < hi:
            return name
    return None


def _lane_meta(snap, lane):
    """화면의 meta() — 레인마다 어디서 이름·민평·체결을 읽는지."""
    if lane == "msb":
        return {"src": snap.get("msb") or [], "names": snap.get("msb_names") or {},
                "ten": snap.get("msb_kind") or {}, "mp": snap.get("msb_mp") or {},
                "fills": snap.get("mfills") or {}, "bench": snap.get("msb_bench") or [],
                "next": [], "alias": snap.get("msb_alias") or {}, "mat_self": True,
                "mats": {}}
    if lane == "nhb":
        return {"src": snap.get("nhb") or [], "names": {}, "ten": {},
                "mp": snap.get("nhb_mp") or {}, "fills": snap.get("nhb_fills") or {},
                "bench": [], "next": [], "alias": snap.get("nhb_label") or {},
                "mat_self": False, "mats": {}}
    return {"src": snap.get("ktb") or [], "names": snap.get("names") or {},
            "ten": snap.get("tenors") or {}, "mp": snap.get("mp") or {},
            "fills": snap.get("kfills") or {}, "bench": snap.get("bench") or [],
            "next": snap.get("nextbench") or [], "alias": {}, "mat_self": False,
            "mats": snap.get("mats") or {}}


def axes(snap, lane, T, mode="def"):
    """레벨 없는 «관심» — 종목·방향·딜러·나이만. [OWNER 2026-09-07]

    책이 아니다. 최우선·스프레드·사다리 어디에도 안 들어간다 — 레벨이 없으니
    넣을 자리가 없다. 「누가 무엇을 하려는가」만 보이는 목록이다.
    수명은 호가와 같은 TTL 을 쓴다(30분).
    """
    out = [e for e in (snap.get("axes") or [])
           if e.get("lane") == lane and alive(e, "ktb", T, mode)]
    return sorted(out, key=lambda e: -e["t"])[:80]


def bond_rows(snap, lane, T, mode="def"):
    """종목별 한 줄. 화면 bondRows 를 그대로 옮긴 것."""
    M = _lane_meta(snap, lane)
    by, all_n = {}, {}
    for e in M["src"]:
        c = e.get("code")
        all_n[c] = all_n.get(c, 0) + 1
        if not alive(e, "ktb", T, mode):
            continue
        by.setdefault(c, []).append(e)
    prev = (snap.get("prev") or {}).get(lane) or {}
    codes = set(by) | set(M["fills"]) | set(prev) | set(M["bench"]) | set(M["next"])
    hist = snap.get("hist") or {}
    rows = []
    for c in codes:
        q = [e for e in by.get(c, []) if e.get("y") is not None]
        aE, bE = uncross(q)
        fa, fb = best_of(aE, bE)
        h = hist.get(c) or []
        mat = c if M["mat_self"] else (M["mats"].get(c) or "")
        ten = ("5년" if lane == "nhb"
               else str(M["ten"].get(c) or "").upper().replace("Y", "년"))
        mid = ((fa["y"] + fb["y"]) / 2 if (fa and fb)
               else (h[-1][1] if h else None))
        rows.append({
            "c": c, "fa": fa, "fb": fb, "mp": M["mp"].get(c), "mat": mat, "ten": ten,
            "nm": (c if lane == "ktb" else (M["names"].get(c) or c)),
            "full": M["names"].get(c) or "", "alias": M["alias"].get(c),
            "bench": c in M["bench"], "next": c in M["next"],
            "fill": M["fills"].get(c), "n": all_n.get(c, 0), "hn": len(h),
            "nq": len(by.get(c, [])), "npx": len(q),
            "mpd": (snap.get("msb_mpd") or {}).get(c), "pv": prev.get(c),
            "mid": mid,
            "today": bool(fa or fb or M["fills"].get(c) or by.get(c) or h),
        })
    if lane == "nhb":
        rows.sort(key=lambda r: (NHBORD.index(r["c"]) if r["c"] in NHBORD else 99,
                                 str(r["c"])))
    else:
        rows.sort(key=lambda r: str(r["mat"] or "9999"))
    return rows


def cr_alive(snap, T, mode="def"):
    return [e for e in (snap.get("credit") or []) if alive(e, "credit", T, mode)]


def bkey(e):
    return f"{e.get('cls') or '회사채'}|{e.get('rt') or '미상'}"


def cr_buckets(snap, T, mode="def"):
    """종별×등급 버킷. 화면 crBuckets 와 같은 정렬(CLSORD, RTORD)."""
    m = {}
    for e in cr_alive(snap, T, mode):
        k = bkey(e)
        b = m.setdefault(k, {"k": k, "cls": e.get("cls") or "회사채",
                             "rt": e.get("rt") or "미상",
                             "est": e.get("rt_src") == "집계",
                             "n": 0, "nat": 0, "bps": [], "ytms": [], "ttms": [],
                             "mb": 0})
        b["n"] += 1
        # ★[OWNER 2026-09-07] «민평에 팔자» 를 0bp 로 받으면(맞다) 버킷의 절반~8할이
        #   0 이 되어 중앙값이 통째로 0 으로 눌린다(실측 버킷마다 민평 52~83%).
        #   중앙값은 «값을 부른 오퍼» 로만 재고, 민평 오퍼는 따로 센다 —
        #   둘은 다른 관측이다(하나는 가격, 하나는 «기준 그 자리»).
        if e.get("atmp"):
            b["nat"] += 1
        elif e.get("bpe") is not None:
            b["bps"].append(e["bpe"])
        if e.get("ytm") is not None:
            b["ytms"].append(e["ytm"])
        if e.get("ttm") is not None:
            b["ttms"].append(e["ttm"])
        b["mb"] += 1 if (e.get("mb") or 0) > 0 else 0
    out = sorted(m.values(),
                 key=lambda b: (CLSORD.index(b["cls"]) if b["cls"] in CLSORD else 99,
                                RTORD.index(b["rt"]) if b["rt"] in RTORD else 99))
    for b in out:                      # 화면이 쓰는 것은 중앙값이다 — 여기서 접는다
        b["bp_med"], b["ytm_med"] = med(b["bps"]), med(b["ytms"])
        b["ttm_lo"] = min(b["ttms"]) if b["ttms"] else None
        b["ttm_hi"] = max(b["ttms"]) if b["ttms"] else None
        del b["bps"], b["ytms"], b["ttms"]
    return out


def heat_cells(snap, T, mode="def"):
    """전일 민평 대비 히트맵. 국고·통안은 (mid − 민평), 크레딧은 문면 민평 대비 bp.

    ★국고·통안 행은 bond_rows 를 다시 접어 쓴다 — 화면 govDeltas 가 그렇게 한다.
    ★칸 값은 중앙값이고, «추정»(끝전 0.5 가정) 건수를 따로 센다.
    """
    cells, est, stale = {}, {}, False
    for lane, row in (("ktb", "국고채"), ("msb", "통안채")):
        for r in bond_rows(snap, lane, T, mode):
            if r["mid"] is None or r["mp"] is None:
                continue
            y = _years_to(snap, r["c"] if lane == "msb" else r["mat"])
            b = bucket_of(y) if y is not None else None
            if not b:
                continue
            if r.get("mpd") and snap.get("mp_date") and \
                    r["mpd"] != str(snap["mp_date"])[:10]:
                stale = True
            # ★키는 «종별|등급|버킷» 세 조각으로 통일한다. 국고·통안은 등급이
            #   없어서 예전엔 두 조각으로 넣었는데, 화면(HMROWS 의 rt=None)은
            #   `미상` 을 끼워 세 조각으로 찾는다 — 그래서 두 행이 늘 비어 있었다.
            cells.setdefault(f"{row}|미상|{b}", []).append((r["mid"] - r["mp"]) * 100)
    for e in cr_alive(snap, T, mode):
        if e.get("ttm") is None or e.get("bpe") is None:
            continue
        b = bucket_of(e["ttm"])
        if not b:
            continue
        k = f"{e.get('cls2') or e.get('cls') or '회사채'}|{e.get('rt') or '미상'}|{b}"
        cells.setdefault(k, []).append(e["bpe"])
        if e.get("lvl") == "est":
            est[k] = est.get(k, 0) + 1
    return {"cells": {k: {"med": med(v), "n": len(v),
                          "lo": min(v), "hi": max(v), "est": est.get(k, 0)}
                      for k, v in cells.items()},
            "stale": stale, "rows": [list(x) for x in HMROWS],
            "buckets": [b[2] for b in BUCKETS]}


def _years_to(snap, mat):
    """만기까지 년수. 기준일은 «책의 날짜» 다 — 리플레이면 그날이다."""
    if not mat:
        return None
    from datetime import date
    try:
        y, m, d = (int(x) for x in str(mat)[:10].split("-"))
        b = str(snap.get("date") or "")[:10].split("-")
        base = date(int(b[0]), int(b[1]), int(b[2]))
        return (date(y, m, d) - base).days / 365.25
    except (ValueError, IndexError, TypeError):
        return None


def mtx_group(cls, rt=None):
    """종별(+등급) -> credit_matrix 의 bond_type. 등급을 안 고르면 «대표 신용등급».
    지방채는 그 표에 없다 — None."""
    if not cls:
        return None
    if cls == "회사채":
        return CB_BY_RT.get(rt, "CB5") if (rt and rt != "미상") else "CB1"
    return MTX_BY_CLS.get(cls)


def cat_counts(snap, T, mode="def"):
    """상단 탭의 숫자. 화면 catCount 와 같은 셈."""
    out = {"main": snap.get("n_msg") or 0, "dyn": snap.get("n_event") or 0,
           "cr": len(cr_alive(snap, T, mode))}
    for lane, src_k, fill_k in (("ktb", "ktb", "kfills"), ("msb", "msb", "mfills"),
                                ("nhb", "nhb", "nhb_fills")):
        s = {e["code"] for e in (snap.get(src_k) or [])
             if alive(e, "ktb", T, mode) and e.get("y") is not None}
        s |= set(snap.get(fill_k) or {})
        out[lane] = len(s)
    return out


def curve_points(snap, T, mode="def"):
    """크레딧 커브의 점과 기준선. 화면 drawCurve 가 하던 계산."""
    off = [e for e in cr_alive(snap, T, mode)
           if e.get("ttm") is not None and e.get("ytm") is not None]
    mp_pts = [(e["ttm"], e["mp"]) for e in cr_alive(snap, T, mode)
              if e.get("ttm") is not None and e.get("mp") is not None]
    bins = {}
    for t, m in mp_pts:
        w = 0.25 if t < 2 else 0.5
        bins.setdefault(round(t / w) * w, []).append(m)
    mp_line = sorted(([b, med(v), len(v)] for b, v in bins.items()),
                     key=lambda x: x[0])
    return {"offers": [{"n": e["n"], "ttm": e["ttm"], "ytm": e["ytm"],
                        "bpe": e.get("bpe"), "a": e.get("a"), "mb": e.get("mb") or 0,
                        "lvl": e.get("lvl")} for e in off],
            "mp_line": mp_line, "mp_n": len(mp_pts)}


def view(snap, lane="ktb", T=None, mode="def", cls=None, rt=None,
         code=None, agg=0.0):
    """한 번에 «화면이 쓸 것» 을 낸다. 화면 상태 중 계산에 영향을 주는 것만 받는다."""
    if T is None:
        now = str(snap.get("now") or "0:0:0").split(":")
        T = int(now[0]) * 3600 + int(now[1]) * 60 + int(now[2])
    out = {"now": snap.get("now"), "T": T, "ttl_mode": mode,
           "counts": cat_counts(snap, T, mode),
           "heat": heat_cells(snap, T, mode)}
    if lane in ("ktb", "msb", "nhb"):
        out["rows"] = bond_rows(snap, lane, T, mode)
        out["axes"] = axes(snap, lane, T, mode)
        # 종목을 고른 상태면 그 종목의 사다리·딜러·교체까지 같이 낸다.
        if code:
            out["ob"] = ob_ladder(snap, lane, code, T, mode, agg)
            out["dealers"] = dealer_cards(snap, lane, code, T, mode)
            out["px"] = px_series(snap, lane, code, T, mode)
            if lane == "ktb":
                out["swap"] = swap_book(snap, code, T, mode)
    elif lane == "cr":
        out["buckets"] = cr_buckets(snap, T, mode)
        out["curve"] = curve_points(snap, T, mode)
        out["mtx_group"] = mtx_group(cls, rt)
        out["grade_curve"] = grade_curve(snap, cls, rt)
        # 고른 종별·등급의 오퍼와 매수 니즈. 화면이 다시 거르지 않게 서버가 낸다.
        out["offers"] = cr_sel(snap, T, mode, cls, rt)
        out["needs"] = cr_needs(snap, T, mode, cls, rt)
    elif lane == "dyn":
        out["pulse"] = pulse_stats(snap, T)
        out["events"] = snap.get("events") or []
        out["event_counts"] = event_counts(snap)
        out["curve_today"] = curve_today(snap, T, mode)
        out["leaderboard"] = leaderboard(snap, cls or "all")
        # v12 공격 방향 — 오퍼가 맞았으면 «사 갔다»(B), 비드가 맞았으면 «팔았다»(S)
        out["aggr"] = snap.get("aggr") or {"B": 0, "S": 0}
    return out


# ── 호가 사다리 ────────────────────────────────────────────────────────────
# 화면 `renderOb` 의 «계산» 절반을 그대로 옮긴 것이다. 막대 폭·나이 칩·툴팁 문구
# 같은 «그리기» 는 화면 몫이라 여기서 하지 않는다 — 그것들은 값이 아니라 표현이다.
#
# ★옮기면서 고치지 않았다. 빈 칸 격자를 «반복 덧셈» 으로 채우는 것까지 JS 와 같다
#   (곱셈으로 바꾸면 부동소수 끝자리가 갈려 지문이 어긋난다).


def bin_of(y, side, agg=0.0):
    """화면 binOf. 집계를 켜면 오퍼는 내림, 비드는 올림으로 칸에 붙인다."""
    if not agg:
        return y
    e = agg / 100.0
    import math
    return (math.floor(y / e + 1e-9) * e) if side == "S" else (math.ceil(y / e - 1e-9) * e)


def _side_acc():
    # hit/fhit = v12 체결 귀속. 그 칸에서 «실제로 체결된» 호가 수와 마지막 체결 시각.
    return {"n": 0, "amt": 0.0, "unk": 0, "dflt": 0, "odd": 0, "atmp": 0,
            "fresh": 0, "hit": 0, "fhit": 0, "who": []}


def ob_ladder(snap, lane, code, T, mode="def", agg=0.0):
    """종목 하나의 호가 사다리.

    반환
      levels   금리 오름차순. 칸마다 {y, S, B, atmp, blank} — S/B 는 그 칸의 집계
      implied  교체에서 나온 내재 호가(조건부라 Σ 에서 뺀다)
      basis    막대 잣대. 'amt' = 억, 'n' = 호가 건수
               ★한 칸이라도 수량을 모르면 억으로 못 그린다 — 그 칸 막대가 0 이 된다
      mx       막대 척도(최댓값). 내재까지 같은 자를 쓴다
      best     최우선 둘과 스프레드·mid
    """
    M = _lane_meta(snap, lane)
    cur = [e for e in M["src"]
           if e.get("code") == code and alive(e, "ktb", T, mode) and e.get("y") is not None]
    a_e, b_e = uncross(cur)
    fa, fb = best_of(a_e, b_e)

    lv = {}
    for e in list(a_e) + list(b_e):
        y = round(bin_of(e["y"], e["s"], agg) * 1e6) / 1e6
        L = lv.setdefault(y, {"S": None, "B": None})
        sd = L[e["s"]] or _side_acc()
        sd["n"] += 1
        if e.get("atmp"):
            sd["atmp"] += 1
        if e.get("a"):
            sd["amt"] += e["a"]
            if e.get("asrc") == "default":
                sd["dflt"] += 1
        else:
            sd["unk"] += 1
            if e.get("asrc") == "oddlot":
                sd["odd"] += 1
        sd["fresh"] = max(sd["fresh"], e["t"])
        if e.get("ft"):
            sd["hit"] += 1
            sd["fhit"] = max(sd["fhit"], e["ft"])
        sd["who"].append(e.get("d"))
        L[e["s"]] = sd

    imp = list((snap.get("implied") or {}).get(code) or [])
    ys = sorted(lv)
    if not ys and not imp:
        return {"code": code, "agg": agg, "levels": [], "implied": [],
                "basis": "n", "mx": 1,
                "sum": {"a": 0.0, "b": 0.0, "na": 0, "nb": 0, "imp_a": 0.0, "imp_b": 0.0},
                "best": {"fa": None, "fb": None, "spread_bp": None, "mid": None}}

    if agg and ys:
        st, full, v = agg / 100.0, [], ys[0]
        while v <= ys[-1] + 1e-9:
            full.append(round(v * 1e6) / 1e6)
            v += st
        ys = full

    all_a = all((not L["S"] or L["S"]["amt"] > 0) and (not L["B"] or L["B"]["amt"] > 0)
                for L in lv.values())
    basis = (lambda sd: sd["amt"]) if all_a else (lambda sd: sd["n"])
    mx = max([1.0]
             + [basis(L[s]) if L[s] else 0 for L in lv.values() for s in ("S", "B")]
             + [(r.get("a") or 0) if all_a else 1 for r in imp])

    levels = []
    for y in ys:
        L = lv.get(y) or {"S": None, "B": None}
        at = bool((L["S"] and L["S"]["atmp"] == L["S"]["n"])
                  or (L["B"] and L["B"]["atmp"] == L["B"]["n"]))
        blank = None
        if not L["S"] and not L["B"] and agg:
            blank = "b" if (fb and y >= fb["y"]) else "a"
        levels.append({"y": y, "S": L["S"], "B": L["B"], "atmp": at, "blank": blank})

    return {
        "code": code, "agg": agg, "levels": levels, "implied": imp,
        "basis": "amt" if all_a else "n", "mx": mx,
        "sum": {"a": sum(e.get("a") or 0 for e in a_e),
                "b": sum(e.get("a") or 0 for e in b_e),
                "na": len(a_e), "nb": len(b_e),
                "imp_a": sum(r.get("a") or 0 for r in imp if r.get("s") == "S"),
                "imp_b": sum(r.get("a") or 0 for r in imp if r.get("s") == "B")},
        "best": {"fa": fa, "fb": fb,
                 "spread_bp": ((fb["y"] - fa["y"]) * 100) if (fa and fb) else None,
                 "mid": ((fa["y"] + fb["y"]) / 2) if (fa and fb) else None},
    }


# ── 딜러 카드 · 교체 책 ────────────────────────────────────────────────────
# 둘 다 화면의 renderDeal·renderSwap 에서 «계산» 만 떼어 온 것이다.
# 정렬 순서까지 같게 두었다 — 순서가 다르면 지문이 어긋난다.


def dealer_cards(snap, lane, code, T, mode="def"):
    """이 종목에 누가 어디 서 있나. 딜러별 «가장 최근» 오퍼/비드 한 건씩."""
    M = _lane_meta(snap, lane)
    cur = [e for e in M["src"] if e.get("code") == code and alive(e, "ktb", T, mode)]
    by = {}
    for e in cur:
        k = e.get("k") or e.get("d")
        r = by.setdefault(k, {"k": k, "d": e.get("d"), "S": None, "B": None})
        s = e.get("s")
        if s in ("S", "B") and (r[s] is None or e["t"] > r[s]["t"]):
            r[s] = e
    ds_by = {d.get("k"): d for d in (snap.get("dealers") or [])}
    ab_all = (snap.get("atbest") or {}).get(code) or {}
    out = []
    for r in by.values():
        ds = ds_by.get(r["k"])
        cn = 0
        if ds:
            for x in (ds.get("codes") or []):
                if x and x[0] == code:
                    cn = x[1]
                    break
        ab = ab_all.get(r["k"]) or [0, 0]
        out.append({**r, "n": cn, "ab_s": ab[0], "ab_b": ab[1],
                    "fresh": max(r["S"]["t"] if r["S"] else 0,
                                 r["B"]["t"] if r["B"] else 0),
                    "both": bool(r["S"] and r["B"])})
    # 화면과 같은 순서: 양면 먼저, 그 다음 신선한 순
    out.sort(key=lambda r: (not r["both"], -r["fresh"]))
    q = [e for e in cur if e.get("y") is not None]
    a_e, b_e = uncross(q)
    fa, fb = best_of(a_e, b_e)
    return {"rows": out, "n": len(out), "n_both": sum(1 for r in out if r["both"]),
            "fa_y": fa["y"] if fa else None, "fb_y": fb["y"] if fb else None}


def swap_book(snap, code, T, mode="def"):
    """교체 책. 신형을 «사는» 쪽이 비드, «파는» 쪽이 오퍼 — 오퍼<비드 불변식 그대로.

    ★레벨은 신형 − 구형 **bp** 다. 아웃라이트처럼 ×100 하면 안 된다.
    """
    rows = [e for e in (snap.get("swap") or [])
            if alive(e, "ktb", T, mode) and (e.get("new") == code or e.get("old") == code)]
    if not rows:
        return None
    byp = {}
    for e in rows:
        byp.setdefault(e.get("pair"), []).append(e)
    pairs = []
    for pair, es in byp.items():
        a_e, b_e = uncross([e for e in es if e.get("y") is not None])
        fa, fb = best_of(a_e, b_e)
        pairs.append({
            "pair": pair,
            "asks": sorted([e for e in es if e.get("s") == "S"],
                           key=lambda x: x["y"] if x.get("y") is not None else 9),
            "bids": sorted([e for e in es if e.get("s") == "B"],
                           key=lambda x: -(x["y"] if x.get("y") is not None else -9)),
            "spread_bp": (fb["y"] - fa["y"]) if (fa and fb) else None,
        })
    return {"n": len(rows), "pairs": pairs}


# ── 크레딧: 고른 버킷의 오퍼 · 매수 니즈 ──────────────────────────────────
# 화면 crSel·crNeeds 를 그대로 옮긴 것. -1 을 내는 JS indexOf 의미까지 맞췄다.


def _idx(seq, x):
    """JS Array.indexOf — 없으면 -1. 파이썬 list.index 는 예외를 던져 쓸 수 없다."""
    try:
        return seq.index(x)
    except ValueError:
        return -1


def cr_sel(snap, T, mode="def", cls=None, rt=None):
    """고른 버킷(cls|rt) 또는 종별의 살아 있는 오퍼. 화면 crSel 그대로.

    ★결과금리가 없는 원 호가는 정렬할 금리가 없다 — 걸러내지 않고 그대로 실어
      보낸다. 화면이 «레벨 미상» 구획으로 따로 모은다 [OWNER].
    """
    rows = cr_alive(snap, T, mode)
    if rt:
        key = f"{cls}|{rt}"
        rows = [e for e in rows if bkey(e) == key]
    elif cls:
        rows = [e for e in rows if (e.get("cls") or "회사채") == cls]
    return sorted(rows, key=lambda e: e["ttm"] if e.get("ttm") is not None else 99)


def cr_needs(snap, T, mode="def", cls=None, rt=None):
    """매수 니즈(바스켓). 종별·등급을 고른 상태면 맞는 것만 남긴다."""
    rows = [e for e in (snap.get("baskets") or []) if alive(e, "credit", T, mode)]
    if not cls:
        return rows
    out = []
    for b in rows:
        secs = set(str(b.get("sec") or "전체").split("|"))
        ok_s = ("전체" in secs) or (cls in secs)
        brt = str(b.get("rt") or "")
        ok_r = (
            not rt
            or rt == "미상"
            or not b.get("rt")
            or brt.find(rt) >= 0
            or (brt.find("이상") >= 0 and _idx(RTORD, rt) >= 0
                and _idx(RTORD, rt) <= _idx(RTORD, brt.replace("이상", "").strip()))
        )
        if ok_s and ok_r:
            out.append(b)
    return out


# ── 동향: 맥박 · 이벤트 · 커브 오늘 · 딜러 리더보드 ────────────────────────
# 화면 renderPulse·renderEvents·renderCurveToday·renderDealers 의 «계산» 절반.
# 막대·선의 픽셀 좌표는 화면 몫이라 여기서는 칸 값만 낸다.


def _ptot(v):
    """화면 pTot — 한 칸의 전체 건수."""
    return (v.get("q") or 0) + (v.get("a") or 0) + (v.get("c") or 0) \
        + (v.get("i") or 0) + (v.get("o") or 0)


def pulse_stats(snap, T):
    """시장 맥박. 칸(기본 10분)별 건수와 «어제 같은 시각 대비»."""
    P = snap.get("pulse") or {}
    bin_s = snap.get("pulse_bin") or 600
    keys = sorted(int(k) for k in P)
    prev = ((snap.get("prev") or {}).get("pulse")) or {}
    pk = sorted(int(k) for k in prev)
    g = lambda d, k: d.get(str(k)) if str(k) in d else d.get(k) or {}

    tot = lambda f: sum((g(P, b).get(f) or 0) for b in keys)
    cut = (T // bin_s) * bin_s
    y_tot = sum(_ptot(g(prev, b)) for b in pk if b <= cut)
    t_tot = sum(_ptot(g(P, b)) for b in keys if b <= cut)
    return {
        "bin": bin_s,
        "bins": [{"t": b, **{f: (g(P, b).get(f) or 0) for f in ("q", "a", "c", "i", "o")}}
                 for b in keys],
        "prev_bins": [{"t": b, "n": _ptot(g(prev, b))} for b in pk],
        "nq": tot("q"), "na": tot("a"), "nc": tot("c"), "ni": tot("i"),
        "ktb": tot("ktb"), "cr": tot("cr"), "msb": tot("msb"),
        # 어제 같은 시각까지의 누적 대비 %. 어느 한쪽이 0 이면 낼 수 없다.
        "vs_prev_pct": ((t_tot / y_tot - 1) * 100) if (y_tot and t_tot) else None,
        "n_dealer": snap.get("n_dealer") if snap.get("n_dealer") is not None
                    else len(snap.get("dealers") or []),
        "prev_n_dealer": (snap.get("prev") or {}).get("n_dealer"),
        "n_event": snap.get("n_event") or 0,
        "t0": keys[0] if keys else None,
        "t1": (keys[-1] + bin_s) if keys else None,
    }


def event_counts(snap):
    """이벤트 종류별 건수. 화면의 필터 배지가 쓴다."""
    out = {}
    for e in (snap.get("events") or []):
        k = e.get("k")
        out[k] = out.get(k, 0) + 1
    return out


def curve_today(snap, T, mode="def"):
    """커브 오늘 — 지표·차기지표의 전일민평 대비. 화면 curveRows 를 옮긴 것."""
    out = {}
    for lane in ("ktb", "msb"):
        M = _lane_meta(snap, lane)
        live = {r["c"]: r for r in bond_rows(snap, lane, T, mode)}
        codes = list(dict.fromkeys(list(M["bench"] or []) + list(M["next"] or [])))
        hist = snap.get("hist") or {}
        rows = []
        for c in codes:
            r = live.get(c)
            if r is None:
                continue
            h = hist.get(c) or []
            last = h[-1] if h else None
            mid = r["mid"] if r.get("mid") is not None else (last[1] if last else None)
            rows.append({**r, "mid": mid,
                         "dbp": ((mid - r["mp"]) * 100)
                                if (mid is not None and r.get("mp") is not None) else None,
                         # hist 꼬리에 실린 «오늘 오퍼·비드 딜러 수»
                         "nd": (f"{last[4]}·{last[5]}" if (last and len(last) > 5) else "")})
        rows.sort(key=lambda r: (_years_to(snap, r.get("mat")) if _years_to(snap, r.get("mat"))
                                 is not None else 99))
        out[lane] = rows
    return out


def leaderboard(snap, lane="all"):
    """딜러 리더보드. 건수 순 — 화면 renderDealers 와 같은 정렬."""
    all_d = snap.get("dealers") or []
    ab = snap.get("atbest") or {}
    ab_tot = {}
    for c in ab:
        for k, v in (ab[c] or {}).items():
            ab_tot[k] = ab_tot.get(k, 0) + (v[0] or 0) + (v[1] or 0)
    rows = []
    for d in all_d:
        ln = d.get("n") if lane == "all" else ((d.get("lane") or {}).get(lane) or 0)
        if lane != "all" and not ln:
            continue
        rows.append({**d, "ln": ln, "ab": ab_tot.get(d.get("k"), 0)})
    rows.sort(key=lambda r: -(r["ln"] or 0))
    return {"rows": rows, "n": snap.get("n_dealer") if snap.get("n_dealer") is not None
            else len(all_d), "shown": len(all_d)}


# ── 시세 이력 ──────────────────────────────────────────────────────────────
# 화면 `drawPx` 의 «계산» 절반. 픽셀 좌표는 화면 몫이지만 **세로 범위**는 여기서
# 낸다 — 그것이 그리기가 아니라 규칙이기 때문이다:
#   [OWNER] 전일 민평이 정중앙을 지나고 그 위아래로 시세가 그려진다(대칭 범위).


def px_series(snap, lane, code, T, mode="def"):
    """종목 하나의 mid 이력과 세로 범위.

    pts  [{t, mid, a(오퍼), b(비드)}]  — T 이후는 잘라낸다
    act  [{t, n, tot}]                 — 활동 막대. n 은 앞 둘의 합(화면과 같게)
    lo/hi  세로 범위. 민평이 있으면 민평 대칭, 없으면 표본 범위에 14% 여백
    """
    M = _lane_meta(snap, lane)
    mp = M["mp"].get(code)
    h = [p for p in ((snap.get("hist") or {}).get(code) or []) if p[0] <= T]
    if len(h) < 2:
        # 화면과 같은 문면을 쓰라고 이유를 실어 보낸다.
        return {"code": code, "mp": mp, "pts": [], "act": [],
                "lo": None, "hi": None, "t0": None, "t1": None,
                "note": "mid 이력 축적 중 · 양방향 호가가 있어야 표본이 쌓입니다"}
    t0 = h[0][0]
    t1 = max(h[-1][0], T)
    if t1 - t0 < 1800:
        t1 = t0 + 1800

    vs = [p[1] for p in h]
    if mp is not None:
        vs.append(mp)
    vs += [p[2] for p in h if len(p) > 3 and p[2] is not None]
    vs += [p[3] for p in h if len(p) > 3 and p[3] is not None]
    if mp is not None:
        dev = max([0.015] + [abs(v - mp) for v in vs]) * 1.14
        lo, hi = mp - dev, mp + dev
    else:
        lo, hi = min(vs), max(vs)
        if hi - lo < 0.03:
            m = (hi + lo) / 2
            lo, hi = m - 0.015, m + 0.015
        pad = (hi - lo) * 0.14
        lo, hi = lo - pad, hi + pad

    act = (snap.get("act") or {}).get(code) or {}
    act_out = []
    for k in sorted(act, key=lambda x: int(x)):
        a = act[k] or [0, 0, 0]
        a = list(a) + [0] * (3 - len(a))
        act_out.append({"t": int(k), "n": (a[0] or 0) + (a[1] or 0),
                        "tot": (a[0] or 0) + (a[1] or 0) + (a[2] or 0)})
    return {
        "code": code, "mp": mp, "lo": lo, "hi": hi, "t0": t0, "t1": t1,
        "bin": snap.get("pulse_bin") or 600,
        "pts": [{"t": p[0], "mid": p[1],
                 "a": (p[2] if len(p) > 3 else None),
                 "b": (p[3] if len(p) > 3 else None)} for p in h],
        "act": act_out,
        "note": None,
    }


# ── 등급 커브 ──────────────────────────────────────────────────────────────
# 스냅샷의 `mtx` 는 `sim_portfolio.credit_matrix` 최신 한 벌이다
# ({date, curves: {bond_type: [[잔존년, 금리], …]}, label}).
# 화면은 «어느 등급 커브를 겹칠지» 만 고르면 되고, 그 선택 규칙(`mtx_group`)은
# 이미 여기 있다 — 커브 자체도 여기서 꺼내 준다.


def grade_curve(snap, cls=None, rt=None):
    """고른 종별·등급에 맞는 등급 민평 커브. 없으면 None."""
    mtx = snap.get("mtx") or {}
    curves = mtx.get("curves") or {}
    g = mtx_group(cls, rt)
    pts = curves.get(g) if g else None
    if not pts:
        return None
    return {"group": g, "date": mtx.get("date"), "label": mtx.get("label"),
            "pts": [{"ttm": p[0], "y": p[1]} for p in pts]}
