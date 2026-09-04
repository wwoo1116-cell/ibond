# -*- coding: utf-8 -*-
"""`kbond_issuer.canon_issuer` 검정.

세 갈래를 본다.
  A. 발전 5사 변형(오탈자·잘린 이름 포함)이 정본 다섯으로만 모이는가
  B. **다섯이 서로 섞이지 않는가** — 이 규칙의 존재 이유다
  C. 접으면 안 되는 이름(아이에스동서·엠캐피탈 …)이 원문으로 남는가
"""
from __future__ import annotations

import sys

from kbond_issuer import POWER5, canon_issuer

# A. 실측 변형 전량 (2026-09-03 머리말 스캔)
FOLD = {
    "한국서부발전": "한국서부발전", "서부발전": "한국서부발전",
    "서부발전팔자": "한국서부발전", "현국서부발전": "한국서부발전",
    "한국서부발전팔자": "한국서부발전", "한국서부잘전": "한국서부발전",
    "한국중부발전": "한국중부발전", "중부발전": "한국중부발전",
    "한국남부발전": "한국남부발전", "남부발전": "한국남부발전",
    "남부잘전": "한국남부발전", "한국남부발": "한국남부발전",
    "국남부발전": "한국남부발전",
    "한국남동발전": "한국남동발전", "남동발전": "한국남동발전",
    "남동팔전": "한국남동발전",
    "한국동서발전": "한국동서발전", "동서발전": "한국동서발전",
    "동서발": "한국동서발전",
    # 회차가 붙은 꼴도 같은 답이어야 한다(머리말·전체 어느 쪽을 줘도)
    "한국서부발전60-1": "한국서부발전", "동서발전 41-2": "한국동서발전",
}

# C. 접으면 안 되는 것 — 민평 검정에서 «다른 발행체» 로 갈린 이름들
KEEP = [
    "아이에스동서",      # IS동서. '동서' 가 들었지만 발전사가 아니다(37행)
    "동서산업", "서부티엔디", "중부도시가스", "남부터미널",
    "엠캐피탈", "아이엠캐피탈",      # 민평 243bp 차 — 절대 한 통이 되면 안 된다
    "한화토탈에너지스", "한화토탈에너지서비스",
    "케이씨씨", "케이씨씨글라스", "하이트진로", "하이트진로홀딩스",
    "SK", "SK온", "한진", "LS", "이마트", "롯데하이마트",
]


def main() -> int:
    bad = []

    for src, want in FOLD.items():
        got, how = canon_issuer(src)
        if got != want or how != "power5":
            bad.append(f"[A] {src!r} -> ({got!r}, {how!r}), 기대 ({want!r}, 'power5')")

    # B. 다섯이 서로 섞이지 않는가 — 변형 전부를 정본별로 모아 교차 확인
    buckets: dict[str, set[str]] = {v: set() for v in POWER5.values()}
    for src, want in FOLD.items():
        got, _ = canon_issuer(src)
        if got in buckets:
            buckets[got].add(want)
    for canon, wants in buckets.items():
        if wants != {canon}:
            bad.append(f"[B] {canon} 통에 섞임: {sorted(wants)}")

    for src in KEEP:
        got, how = canon_issuer(src)
        if how != "raw" or got != src:
            bad.append(f"[C] {src!r} 가 접혔다 -> ({got!r}, {how!r})")

    for src in (None, "", "   "):
        got, how = canon_issuer(src)
        if got is not None or how is not None:
            bad.append(f"[D] 빈 입력 {src!r} -> ({got!r}, {how!r})")

    n = len(FOLD) + len(buckets) + len(KEEP) + 3
    if bad:
        print(f"FAIL {len(bad)}/{n}")
        for b in bad:
            print("   ", b)
        return 1
    print(f"PASS {n}/{n}  (접기 {len(FOLD)} · 비혼합 {len(buckets)} · 원문유지 {len(KEEP)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
