# -*- coding: utf-8 -*-
"""구운 CSS 의 폰트 주소에 접두어를 붙인다. [2026-09-11]

★왜 — Next 의 `basePath` 는 **CSS 안의 `url(/fonts/...)` 를 안 고친다.** 절대 주소라
  Funnel 루트(다른 앱)로 새 나가 404 가 되고, 한글이 시스템 글꼴로 떨어진다
  (2026-09-11 실측: `/fonts/PretendardVariable.woff2` 404).

★왜 파이썬인가 — 같은 치환을 PowerShell 안에서 하려니 따옴표가 세 겹으로 겹쳐
  Windows PowerShell 5.1 파서가 문자열을 끊어 먹었다(세 번 시도, 세 번 다른 오류).
  배관 하나 고치자고 셸 따옴표와 싸우지 않는다.

사용:  python fix_font_prefix.py out-kbond /kbond/app
"""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "out-kbond")
    base = sys.argv[2] if len(sys.argv) > 2 else "/kbond/app"
    css_dir = out / "_next" / "static" / "css"
    if not css_dir.is_dir():
        print(f"  [건너뜀] CSS 폴더가 없다: {css_dir}")
        return 0
    n_file = n_hit = 0
    for f in sorted(css_dir.glob("*.css")):
        t = f.read_text(encoding="utf-8")
        hit = t.count("url(/fonts/") + t.count("url('/fonts/")
        if not hit:
            continue
        t = t.replace("url(/fonts/", f"url({base}/fonts/")
        t = t.replace("url('/fonts/", f"url('{base}/fonts/")
        f.write_text(t, encoding="utf-8")
        n_file += 1
        n_hit += hit
    print(f"  폰트 주소 {n_hit}곳 고침 ({n_file}개 파일) -> {base}/fonts/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
