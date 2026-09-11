# 오너 PC 가 서빙할 «접두어 빌드» 를 굽는다. [2026-09-11]
#
# Vercel 판(루트)과 Funnel 판(/kbond/app)은 자산 주소가 달라 한 빌드로 둘 다 못 낸다.
# 여기서는 Funnel 판을 굽어 out-kbond 에 두고, 이어서 Vercel 판을 되굽는다.
# kbond_api 가 out-kbond 를 /app 과 /kbond/app 두 자리에 붙인다 - 둘 다 필요하다.
# Tailscale 은 /kbond 를 떼고 넘기지만 브라우저는 떼기 전 주소로 자산을 부른다.
#
#   powershell -NoProfile -File build_app.ps1
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$env:KBOND_BASE_PATH = '/kbond/app'
Write-Host "[1/3] next build (basePath=$env:KBOND_BASE_PATH)"
npm run build
if ($LASTEXITCODE -ne 0) { throw "build failed" }

Write-Host "[2/3] out -> out-kbond + font prefix"
if (Test-Path out-kbond) { Remove-Item out-kbond -Recurse -Force }
Move-Item out out-kbond
# CSS 안의 폰트 주소는 Next 의 basePath 가 안 고쳐 준다 - 파이썬이 고친다
# (셸 따옴표 세 겹과 싸우지 않는다. fix_font_prefix.py 머리말 참조).
python fix_font_prefix.py out-kbond /kbond/app
if ($LASTEXITCODE -ne 0) { throw "font prefix failed" }

Write-Host "[3/3] rebuild for Vercel (no prefix)"
Remove-Item Env:\KBOND_BASE_PATH
npm run build
if ($LASTEXITCODE -ne 0) { throw "build failed" }
Write-Host "    done - out (Vercel) / out-kbond (Funnel)"
