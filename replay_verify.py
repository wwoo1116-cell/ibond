# -*- coding: utf-8 -*-
"""리플레이 서버를 동결 시점에 띄우고 verify_v4 를 돌린다.
   python replay_verify.py 20260902 15:00:00 [port] [--keep]"""
import subprocess, sys, time, urllib.request, os, signal
from pathlib import Path

day, at = sys.argv[1], sys.argv[2]
port = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3].isdigit() else "8302"
keep = "--keep" in sys.argv
APP = Path(r"C:\Users\infomax\Projects\apps\kbond")
SP = Path(__file__).parent
env = dict(os.environ, PYTHONUTF8="1")

# 같은 포트의 옛 리플레이를 죽인다
subprocess.run(["powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                f"Where-Object {{ $_.CommandLine -like '*--port {port}*' }} | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
               capture_output=True)
time.sleep(0.5)
out = open(SP / f"replay_{port}.out", "w", encoding="utf-8")
p = subprocess.Popen([sys.executable, "kbond_live.py", "--replay", day, "--at", at,
                      "--port", port, "--viewer", str(APP / "kbond_live.html")]
                     + ([] if "--mask" in sys.argv else ["--no-mask"]),
                     cwd=str(APP), stdout=out, stderr=subprocess.STDOUT, env=env,
                     creationflags=0x00000008)  # DETACHED_PROCESS
t0 = time.time()
ok = False
while time.time() - t0 < 180:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
            if r.status == 200:
                ok = True
                break
    except Exception:
        pass
    if p.poll() is not None:
        break
    time.sleep(1.0)
if not ok:
    out.close()
    print("서버가 뜨지 않음 · 로그:")
    print((SP / f"replay_{port}.out").read_text(encoding="utf-8")[-3000:])
    sys.exit(2)
print(f"서버 기동 {time.time() - t0:.1f}초 (port {port}, {day} @{at})")
r = subprocess.run([sys.executable, "verify_v4.py", "--port", port, "--at", at, "--day", day],
                   cwd=str(APP), capture_output=True, text=True, env=env, encoding="utf-8")
print(r.stdout[-6000:])
if r.stderr.strip():
    print("STDERR:", r.stderr[-2000:])
if not keep:
    try:
        p.kill()
    except Exception:
        pass
sys.exit(r.returncode)
