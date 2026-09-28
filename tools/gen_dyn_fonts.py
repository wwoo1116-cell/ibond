# -*- coding: utf-8 -*-
"""Pretendard 변수 글꼴을 한국어 «동적 조각» 으로 자른다. [2026-09-28 경량화]

왜 — 첫 화면 3.9MB 중 `PretendardVariable.woff2` 하나가 2,057,688B(53%)였다. 화면에
있는 글자는 몇백 자인데 11,172 음절을 전부 받고 있었다. 조각을 내면 브라우저는
`unicode-range` 에 걸리는 조각만 받는다(보통 15~25장, 300~500KB).

조각 경계는 Google Fonts 가 한국어 글꼴에 쓰는 124 조각(사용 빈도순)을 그대로 쓴다 —
`fonts-src/korean-slices.css` 에 받아 둔 것(Noto Sans KR 의 css2 응답, 2026-09-28).
글꼴 자체·축 범위(45 930)·font-display(block) 는 `type.css` 에 있던 선언 그대로다.

    python tools/gen_dyn_fonts.py          (kbond-web 에서 · 30초 · fontTools+brotli)

산출 — public/fonts/dyn/PretendardVariable.N.woff2 (96장) · src/theme/pretendard-dyn.css
⚠원본 글꼴은 `tools/fonts-src/` 에 있다(public/ 에 두면 그대로 배달된다).
"""
from __future__ import annotations

import re
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent
SRC = WEB / "tools" / "fonts-src" / "PretendardVariable.woff2"
SLICES = WEB / "tools" / "fonts-src" / "korean-slices.css"
OUT = WEB / "public" / "fonts" / "dyn"
CSS = WEB / "src" / "theme" / "pretendard-dyn.css"
TTF = Path(tempfile.gettempdir()) / "Pretendard.src.ttf"   # woff2 해독은 장당 20초라 한 번만


def cps(r: str) -> set[int]:
    out: set[int] = set()
    for tok in r.replace(" ", "").split(","):
        m = re.fullmatch(r"U\+([0-9A-Fa-f]+)(?:-([0-9A-Fa-f]+))?", tok)
        if not m:
            raise ValueError(tok)
        a = int(m.group(1), 16)
        b = int(m.group(2), 16) if m.group(2) else a
        out.update(range(a, b + 1))
    return out


def one(args):
    i, r = args
    from fontTools import subset
    from fontTools.ttLib import TTFont
    font = TTFont(str(TTF))
    want = cps(r) & set(font.getBestCmap())
    if not want:                                   # 이 글꼴에 없는 구간(CJK 호환 등)
        return (i, None, r, 0, 0)
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.hinting = False
    opts.notdef_outline = True
    opts.name_IDs = ["*"]
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=want)
    sub.subset(font)
    name = f"PretendardVariable.{i}.woff2"
    p = OUT / name
    font.flavor = "woff2"
    font.save(str(p))
    return (i, name, r.strip(), p.stat().st_size, len(want))


def main() -> int:
    from fontTools.ttLib import TTFont
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.woff2"):
        old.unlink()
    f = TTFont(str(SRC))
    f.flavor = None
    f.save(str(TTF))
    ranges = re.findall(r"unicode-range:\s*([^;]+);", SLICES.read_text(encoding="utf-8"))
    with ProcessPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(one, list(enumerate(ranges))))
    blocks = [b for b in res if b[1]]
    total = sum(b[3] for b in blocks)
    print(f"  {len(blocks)}/{len(ranges)} 조각 · {total:,}B · {time.time() - t0:.0f}초")

    css = [
        "/* Pretendard SR — 동적 조각 [2026-09-28 경량화]. `tools/gen_dyn_fonts.py` 가 만든다. 손으로 고치지 않는다.",
        " * 조각 경계는 Google Fonts 한국어 124 조각(사용 빈도순)을 그대로 쓴다 — 브라우저는 화면에 실제로",
        " * 있는 글자의 조각만 받는다. 한 파일(2,057,688B)을 매번 다 받던 것을 대신한다. 글꼴·축 범위·",
        " * font-display 는 type.css 에 있던 선언 그대로다. */",
        "",
    ]
    for i, name, r, n, k in blocks:
        css += [
            "@font-face {",
            "  font-family: 'Pretendard SR';",
            "  font-weight: 45 930;",
            "  font-style: normal;",
            "  font-display: block;",
            f"  src: url('/fonts/dyn/{name}') format('woff2');",
            f"  unicode-range: {r};",
            "}",
            "",
        ]
    CSS.write_text("\n".join(css), encoding="utf-8")
    print(f"  -> {CSS.relative_to(WEB)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
