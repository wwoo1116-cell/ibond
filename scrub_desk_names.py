# -*- coding: utf-8 -*-
"""주석·문서의 «거래상대 데스크명 + 전화번호» 를 가린다 [OWNER 2026-09-09 「가리고 푸시」].

## 왜

이 프로젝트는 화면에서 딜러를 `H09-10` 으로 가린다(`verify_v4 [H]` 가 그걸 검사한다).
그런데 **소스 주석과 문서에는** 레인 이력 동안 실제 예시가 그대로 쌓였다.

    [증권사 채권시장1팀 (02-XXXX-XXXX)]   <증권사 XXXX-XXXX>
    증권사 FICC SALES XXXX-XXXX          (증권사 CMS XXXX-XXXX)

리포를 기계 밖(GitHub)으로 올리면 이건 거래상대의 실명·연락처가 같이 나가는 것이다.
비공개 저장소여도 마찬가지다.

## 무엇을 안 건드리나

**정규식·패턴 문자열은 손대지 않는다.** 파서가 그걸로 전화번호를 찾아 브로커를 떼기
때문이다(`RE_PHONE` 등). 가리는 건 «예시로 적힌 문면» 뿐이다.

그래서 다음 셋만 바꾼다.

    1. 전화번호꼴  02-XXXX-XXXX · XXXX-XXXX   ->  XXXX-XXXX 꼴
    2. 증권사명    증권사 이름 …            ->  증권A · 증권B …
    3. 사람 이름   (거의 없다 — 있으면 손으로 지운다)

⚠ 「번호처럼 생긴 것」에는 **회차(24-10)·민평(3.665)·만기(25.6.12)** 가 섞여 있다.
  그래서 번호는 «데스크명이 앞에 있을 때» 만 가린다. 그 판단이 안 서면 안 건드린다.

실행:  python scrub_desk_names.py --dry     (무엇이 바뀌는지만 본다)
       python scrub_desk_names.py           (실제로 고친다)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent

# ★서명 묶음만 가린다 — 괄호·대괄호·꺾쇠 안에 **전화번호가 들어 있는** 덩어리.
#   그 안의 이름과 번호를 통째로 바꾼다.
#
# ⚠★데스크명을 전역 치환하면 안 된다. 「한화」·「삼성」·「신한투자증권」은 **발행체
#   이름**이기도 해서(한화토탈에너지스·삼성카드·신한투자증권 회사채) 사전과 검정이
#   망가진다. 실제로 첫 시안이 그랬다 — 연습 실행에서 잡았다.
#
# ⚠정규식·패턴 문자열은 안 건드린다. 파서가 그걸로 브로커를 떼기 때문이다.
#   그래서 «서명처럼 생긴 덩어리» 만 본다: 여는 기호 + 20자 이내 + 전화번호 + 닫는 기호.
RE_TEL = r"(?:☎|☏|\s)*(?:0\d{1,2}[-.\s])?\d{3,4}\s*[-.\s~/]\s*\d{3,4}(?:\s*[~/]\s*\d{1,4})?"
_INNER = r"[^\]\)>}\n]"
RE_SIGN = re.compile(
    r"([\[\(<{▨])"                          # 여는 기호
    + _INNER + r"{0,28}?"                   # 안쪽 (데스크명·부서)
    + r"(" + RE_TEL + r")"                  # 전화번호
    + _INNER + r"{0,6}?"                    # 꼬리
    + r"([\]\)>}▨])")                       # 닫는 기호


def scrub(text: str):
    """(고친 글, 바뀐 건수). 서명 묶음 안만 가린다."""
    n = 0

    def one(m):
        nonlocal n
        n += 1
        # 통째로 «서명» 이라고만 남긴다 — 이름도 번호도 안 남긴다.
        return m.group(1) + "서명 XXXX-XXXX" + m.group(3)

    return RE_SIGN.sub(one, text), n


TARGETS = sorted(
    [p for p in HERE.iterdir()
     if p.suffix in (".py", ".md") and not p.name.endswith(".bak")
     and p.name != Path(__file__).name])

if __name__ == "__main__":
    dry = "--dry" in sys.argv
    tot = 0
    for p in TARGETS:
        try:
            raw = p.read_bytes()
            s = raw.decode("utf-8")
        except Exception:
            continue
        out, n = scrub(s)
        if out == s:
            continue
        tot += 1
        print(f"  {p.name:34s} 번호 {n}건 · 이름 치환")
        if not dry:
            crlf = raw.count(b"\r\n") > 0
            body = out.replace("\r\n", "\n")
            p.write_bytes(body.replace("\n", "\r\n" if crlf else "\n").encode("utf-8"))
    print(f"\n{'(연습)' if dry else '고침'} 파일 {tot}개")
