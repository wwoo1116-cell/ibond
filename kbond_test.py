# -*- coding: utf-8 -*-
"""
K-Bond(케이본드) 메신저 텍스트 추출 가능성 테스트

  Test 1  : pywinauto attach -> print_control_identifiers() -> kbond_ui_tree.txt
  Test 2  : 창 활성화 -> pyautogui Ctrl+A / Ctrl+C -> pyperclip 회수
  Test 2b : (진단 보강) 채팅 로그 컨트롤에 직접 포커스를 준 뒤 Ctrl+A / Ctrl+C
  Test 3  : (보너스) WM_GETTEXT 로 채팅 로그 컨트롤 텍스트 직접 읽기
"""
import ctypes
import io
import os
import subprocess
import sys
import time

# ---------------------------------------------------------------- 0. 패키지
REQUIRED = ["pywinauto", "pyautogui", "pyperclip"]


def ensure_packages():
    missing = []
    for pkg in REQUIRED:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"[SETUP] 설치 필요: {missing}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
    else:
        print(f"[SETUP] 필요 패키지 모두 존재: {REQUIRED}")


ensure_packages()

import pyautogui          # noqa: E402
import pyperclip          # noqa: E402
import win32con           # noqa: E402
import win32gui           # noqa: E402
import win32process       # noqa: E402
from pywinauto import Application  # noqa: E402

pyautogui.FAILSAFE = False
user32 = ctypes.windll.user32

WM_GETTEXT, WM_GETTEXTLENGTH, WM_COPY, EM_SETSEL = 0x000D, 0x000E, 0x0301, 0x00B1

HERE = os.path.dirname(os.path.abspath(__file__))
TREE_PATH = os.path.join(HERE, "kbond_ui_tree.txt")
KEYWORDS = ("케이본드", "K-Bond", "K-BOND", "KBond", "k-bond")

# uia 백엔드는 이 앱에서 트리가 폭주한다(무제한 시 421MB). 깊이를 못 박는다.
UIA_DEPTH = 4
SENTINEL = "__KBOND_SENTINEL__"
MAX_LINE = 400   # 트리 덤프 한 줄 최대 길이


def sep(title):
    print("\n" + "=" * 74)
    print(title)
    print("=" * 74)


def proc_name(pid):
    try:
        import psutil
        return psutil.Process(pid).name()
    except Exception:
        return "?"


# ---------------------------------------------------------- 1. 타겟 창 찾기
def enum_windows():
    out = []

    def cb(hwnd, _):
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            return
        out.append({
            "hwnd": hwnd, "pid": pid,
            "title": win32gui.GetWindowText(hwnd),
            "cls": win32gui.GetClassName(hwnd),
            "visible": bool(win32gui.IsWindowVisible(hwnd)),
        })

    win32gui.EnumWindows(cb, None)
    return out


def find_targets():
    """요구사항대로 제목 매칭을 먼저 하고, 그 창이 숨겨져 있으면(트레이 상주)
    같은 프로세스의 보이는 대화방 창까지 대상으로 확장한다."""
    wins = enum_windows()
    by_title = [w for w in wins
                if any(k in w["title"] for k in KEYWORDS)
                and proc_name(w["pid"]).lower().startswith("kbond")]
    print(f"[FIND] 제목 매칭 창 {len(by_title)}개")
    for w in by_title:
        print(f"        hwnd={w['hwnd']} vis={w['visible']} "
              f"class={w['cls']} title={w['title']!r}")

    pids = {w["pid"] for w in by_title}
    if not pids:
        pids = {w["pid"] for w in wins
                if proc_name(w["pid"]).lower().startswith("kbond")}
        print(f"[FIND] 제목 매칭 실패 -> 프로세스명 폴백, pid={pids}")
    if not pids:
        return None, [], []

    pid = sorted(pids)[0]
    visible = [w for w in wins if w["pid"] == pid and w["visible"]
               and w["title"] and w["cls"] != "TApplication"]
    print(f"[FIND] pid={pid} ({proc_name(pid)}) 의 보이는 대화방 창 {len(visible)}개")
    for w in visible:
        print(f"        hwnd={w['hwnd']} class={w['cls']} title={w['title']!r}")

    cand = [w for w in by_title if w["visible"]] or visible or by_title
    return pid, cand, visible


def descendants(hwnd):
    kids = []
    try:
        win32gui.EnumChildWindows(hwnd, lambda h, _: kids.append(h), None)
    except Exception:
        pass
    return kids


def get_text(hwnd):
    n = user32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 2)
    user32.SendMessageW(hwnd, WM_GETTEXT, n + 2, buf)
    return buf.value


def chat_log_control(hwnd):
    """대화 로그 컨트롤 = Edit 계열 자식 중 텍스트가 가장 긴 것."""
    best, best_len, best_cls = None, 0, ""
    for k in descendants(hwnd):
        cls = win32gui.GetClassName(k)
        if "edit" not in cls.lower():
            continue
        n = user32.SendMessageW(k, WM_GETTEXTLENGTH, 0, 0)
        if n > best_len:
            best, best_len, best_cls = k, n, cls
    return best, best_cls, best_len


# --------------------------------------------------- 2. Test 1 : pywinauto
def dump_tree(fh, backend, pid, hwnds, depth=None):
    fh.write(f"\n{'#' * 72}\n# BACKEND = {backend}   (depth={depth})\n{'#' * 72}\n")
    try:
        app = Application(backend=backend).connect(process=pid, timeout=10)
    except Exception as e:
        msg = f"[Test1/{backend}] connect 실패: {type(e).__name__}: {e}"
        print("  " + msg)
        fh.write(msg + "\n")
        return 0
    ok = 0
    for h in hwnds:
        fh.write(f"\n{'=' * 72}\n=== hwnd={h} "
                 f"{win32gui.GetWindowText(h)!r} ===\n{'=' * 72}\n")
        try:
            buf, old = io.StringIO(), sys.stdout
            sys.stdout = buf
            try:
                app.window(handle=h).print_control_identifiers(depth=depth)
            finally:
                sys.stdout = old
            # win32 백엔드는 컨트롤 텍스트를 통째로(33만자) 그리고 중복해서
            # 찍는다. 무제한이면 파일이 400MB 를 넘으므로 줄 단위로 자른다.
            for ln in buf.getvalue().splitlines():
                fh.write(ln[:MAX_LINE] +
                         (f"  ...[{len(ln) - MAX_LINE}자 생략]" if len(ln) > MAX_LINE else "") +
                         "\n")
            ok += 1
        except Exception as e:
            err = f"[ERROR] {type(e).__name__}: {e}"
            print(f"  [Test1/{backend}] hwnd={h} {err}")
            fh.write(err + "\n")
    return ok


def test1(pid, targets, visible):
    sep("TEST 1 : pywinauto  print_control_identifiers()")
    hwnds = []
    for w in targets + visible:
        if w["hwnd"] not in hwnds:
            hwnds.append(w["hwnd"])
    try:
        with open(TREE_PATH, "w", encoding="utf-8") as fh:
            fh.write(f"K-Bond UI tree dump  pid={pid} ({proc_name(pid)})\n")
            fh.write(f"대상 hwnd: {hwnds}\n")
            n1 = dump_tree(fh, "win32", pid, hwnds)
            n2 = dump_tree(fh, "uia", pid, hwnds, depth=UIA_DEPTH)
        size = os.path.getsize(TREE_PATH)
        print(f"[Test1] 저장 -> {TREE_PATH}  ({size:,} bytes, "
              f"win32 {n1}창 / uia {n2}창)")
        return True
    except Exception as e:
        print(f"[Test1] 실패: {type(e).__name__}: {e}")
        return False


# ------------------------------------------------- 3. Test 2 : 클립보드
def activate(hwnd):
    """포그라운드 잠금을 뚫기 위해 AttachThreadInput + ALT 트릭까지 쓴다."""
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        for attempt in range(3):
            cur = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
            tgt = user32.GetWindowThreadProcessId(hwnd, None)
            user32.AttachThreadInput(cur, tgt, True)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetActiveWindow(hwnd)
            user32.AttachThreadInput(cur, tgt, False)
            time.sleep(0.4)
            if win32gui.GetForegroundWindow() == hwnd:
                return True
            pyautogui.keyDown("alt"); pyautogui.keyUp("alt")   # 포그라운드 잠금 해제
        return win32gui.GetForegroundWindow() == hwnd
    except Exception as e:
        print(f"  [WARN] 활성화 실패 hwnd={hwnd}: {type(e).__name__}: {e}")
        return False


def fg_desc(hwnd):
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return f"{proc_name(pid)} / {win32gui.GetWindowText(hwnd)!r}"
    except Exception:
        return "?"


def copy_and_read(focus_hwnd=None):
    """Ctrl+A, Ctrl+C 를 보내고 클립보드를 회수한다."""
    pyperclip.copy(SENTINEL)
    if focus_hwnd:
        top = win32gui.GetAncestor(focus_hwnd, 2)
        cur = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
        tgt = user32.GetWindowThreadProcessId(top, None)
        user32.AttachThreadInput(cur, tgt, True)
        user32.SetFocus(focus_hwnd)
        user32.AttachThreadInput(cur, tgt, False)
        time.sleep(0.3)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "c")
    time.sleep(0.5)
    try:
        txt = pyperclip.paste()
    except Exception as e:
        print(f"  클립보드 읽기 예외: {type(e).__name__}: {e}")
        return ""
    return "" if txt == SENTINEL else txt


def test2(candidates):
    sep("TEST 2 : 창 활성화 + Ctrl+A / Ctrl+C + 클립보드 회수")
    results = {}
    for w in candidates:
        label = f"{w['title']} (hwnd={w['hwnd']})"
        print(f"\n--- 대상: {w['cls']} / {label}")
        ok_fg = activate(w["hwnd"])
        time.sleep(1.0)
        fg = win32gui.GetForegroundWindow()
        if fg != w["hwnd"]:
            print(f"  [무효] 포그라운드가 hwnd={fg} "
                  f"({fg_desc(fg)}) 로 남음 - 이 창의 결과는 신뢰할 수 없음")
            results[label] = None
            continue
        print(f"  포그라운드 hwnd={fg} (일치)")

        txt = copy_and_read()                        # (a) 창만 활성화
        how = "창 활성화만"
        if not txt:                                  # (b) 로그 컨트롤에 포커스
            log, cls, _ = chat_log_control(w["hwnd"])
            if log:
                print(f"  -> 재시도(Test 2b): {cls} hwnd={log} 에 직접 포커스")
                txt = copy_and_read(focus_hwnd=log)
                how = f"{cls} 직접 포커스"
        if txt:
            print(f"  [OK/{how}] 클립보드 {len(txt):,}자 획득. 앞 500자:")
            print("  " + "-" * 62)
            print(txt[:500])
            print("  " + "-" * 62)
            results[label] = txt
        else:
            print("  클립보드 복사 실패(보안 모듈 차단 의심)")
            results[label] = None
    return results


# ------------------------------- 4. Test 3 : WM_GETTEXT 직접 읽기(보너스)
def test3(candidates):
    sep("TEST 3 (보너스) : WM_GETTEXT 로 채팅 로그 컨트롤 직접 읽기")
    results = {}
    for w in candidates:
        log, cls, n = chat_log_control(w["hwnd"])
        if not log:
            print(f"  {w['title']:<16} Edit 계열 자식 없음")
            results[w["title"]] = None
            continue
        txt = get_text(log)
        lines = txt.splitlines()
        print(f"\n  {w['title']}  [{cls} hwnd={log}]  {len(txt):,}자 / {len(lines):,}행")
        for ln in lines[-3:]:
            print(f"      {ln[:110]}")
        results[w["title"]] = txt
    return results


# ------------------------------------------------------------------ main
if __name__ == "__main__":
    pid, targets, visible = find_targets()
    if pid is None:
        print("\n[FATAL] 케이본드/K-Bond 창을 찾지 못했습니다.")
        sys.exit(1)

    t1 = test1(pid, targets, visible)

    cands, seen = [], set()
    for w in targets + visible:
        if w["visible"] and w["hwnd"] not in seen:
            seen.add(w["hwnd"])
            cands.append(w)

    t2 = test2(cands)
    t3 = test3(cands)

    sep("요약")
    print(f"Test 1  UI 트리 저장 : {'성공' if t1 else '실패'} -> {TREE_PATH}")
    print(f"Test 2  클립보드     : {sum(1 for v in t2.values() if v)}/{len(t2)} 창 성공")
    for k, v in t2.items():
        print(f"          {'OK  ' if v else 'FAIL'} {k}")
    print(f"Test 3  WM_GETTEXT   : {sum(1 for v in t3.values() if v)}/{len(t3)} 창 성공")
    for k, v in t3.items():
        print(f"          {'OK  ' if v else 'FAIL'} {k:<16} "
              f"{len(v) if v else 0:>9,}자")
