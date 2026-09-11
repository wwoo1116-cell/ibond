# K-Bond 백엔드 재기동. [2026-09-11]
#
# 왜 스크립트가 필요한가 — `Stop-ScheduledTask -TaskName KBondLive` 는 **파이썬을
# 안 죽인다**. 태스크의 실행 파일이 `conhost.exe --headless`(콘솔 창을 없애려고
# 그렇게 걸어 뒀다) 이고, 태스크 엔진은 그 래퍼만 종료 대상으로 본다. 그래서
# Stop → Start 를 하면 옛 프로세스가 :8301 을 물고 살아 있고 새 인스턴스는
# 「주소가 이미 사용 중」으로 **조용히 죽는다**(2026-09-11 실측).
#
# 그래서 여기서는 포트를 물고 있는 프로세스를 직접 죽이고 태스크를 다시 시작한다.
#
#   powershell -NoProfile -File restart_kbond.ps1
#
# 책은 로그에서 다시 세운다(기동 때 그날 로그를 통째로 읽는다) — 재기동으로
# 잃는 것은 없고, 몇 초 동안만 화면이 빈다.
param([int]$Port = 8301, [string]$Task = 'KBondLive')

$ErrorActionPreference = 'Stop'

Write-Host "[1/4] 태스크 정지 — $Task"
try { Stop-ScheduledTask -TaskName $Task } catch { Write-Host "      (정지할 인스턴스 없음)" }
Start-Sleep -Seconds 1

Write-Host "[2/4] :$Port 를 물고 있는 프로세스 정리"
$owners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
          Select-Object -ExpandProperty OwningProcess -Unique
foreach ($procId in $owners) {
    $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($p) {
        Write-Host "      kill $($p.ProcessName) ($procId)"
        Stop-Process -Id $procId -Force
    }
}
Start-Sleep -Seconds 2

Write-Host "[3/4] 태스크 시작"
Start-ScheduledTask -TaskName $Task

Write-Host "[4/4] 기동 확인"
# ★기다리는 시간이 넉넉해야 한다 — 기동은 그날 로그를 통째로 되감는 일이라
#   장이 끝나갈수록 오래 걸린다(2026-09-11 11:22 실측 61초, 메시지 5,392건).
$ok = $false
foreach ($i in 1..90) {
    Start-Sleep -Seconds 2
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/view?lane=cr" -UseBasicParsing -TimeoutSec 5
        if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch { }
}
if ($ok) {
    $j = (Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/view?lane=cr" -UseBasicParsing).Content | ConvertFrom-Json
    Write-Host "      떴습니다 — 책 시각 $($j.now) · 메시지 $($j.counts.main) · 크레딧 $($j.counts.cr)"
    exit 0
}
Write-Host "      ★안 떴습니다. 로그를 보세요: C:\Users\infomax\Projects\data\kbond\kbond_live_server.log"
exit 1
