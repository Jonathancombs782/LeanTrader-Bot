# Robust background starter for uvicorn (works on Windows PowerShell 5.1)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$cwd = (Get-Location).Path
$python = Join-Path $cwd ".\venv\Scripts\python.exe"
if (-Not (Test-Path $python)) { Write-Host "Python not found at $python"; exit 2 }

$runtimeDir = Join-Path $cwd 'runtime'
if (-Not (Test-Path $runtimeDir)) { New-Item -ItemType Directory -Path $runtimeDir | Out-Null }
$logPath = Join-Path $runtimeDir 'uvicorn.log'

# Build command to run in new powershell process. Use -u for unbuffered output.
$innerCmd = "& '$python' -u -m uvicorn 'leantrader.api.app:app' --reload --host 127.0.0.1 --port 8000 > '$logPath' 2>&1"
Write-Host "Starting uvicorn in background via new PowerShell process; log -> $logPath"
Start-Process -FilePath 'powershell' -ArgumentList '-NoProfile','-WindowStyle','Hidden','-Command',$innerCmd -PassThru | Out-Null
Start-Sleep -Seconds 2

if (Test-Path $logPath) { Write-Host "Started. Tail of log:"; Get-Content -Path $logPath -Tail 200 | ForEach-Object { Write-Host $_ } } else { Write-Host "Started, but no log yet at $logPath" }
Write-Host "Background start requested. Check $logPath for runtime logs."
