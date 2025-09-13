# Start uvicorn in background and redirect logs to runtime/uvicorn.log
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$runtimeDir = Join-Path (Get-Location) 'runtime'
if (-Not (Test-Path $runtimeDir)) { New-Item -ItemType Directory -Path $runtimeDir | Out-Null }
$outLog = Join-Path $runtimeDir 'uvicorn.log'

Write-Host "Stopping existing uvicorn/python processes..."
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -match 'uvicorn' -or $_.CommandLine -match 'python' -and $_.CommandLine -match 'leantrader.api.app') }
if ($procs) { foreach ($p in $procs) { Write-Host "Stopping PID" $p.ProcessId; Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue } }

$python = Join-Path (Get-Location) '.\venv\Scripts\python.exe'
if (-Not (Test-Path $python)) { Write-Host "Python not found at $python"; exit 2 }

$uvArgs = '-m uvicorn "leantrader.api.app:app" --reload --host 127.0.0.1 --port 8000'
Write-Host "Starting uvicorn: $python $uvArgs"

# Start uvicorn and redirect output to a logfile using Start-Process
Start-Process -FilePath $python -ArgumentList $uvArgs -RedirectStandardOutput $outLog -RedirectStandardError $outLog -NoNewWindow -WindowStyle Hidden -PassThru | Out-Null
Start-Sleep -Seconds 3
Write-Host "Started uvicorn; waiting 3s for logs..."

# Dump the log
if (Test-Path $outLog) { Write-Host "---- uvicorn.log (last 200 lines) ----"; Get-Content -Path $outLog -Tail 200 | ForEach-Object { Write-Host $_ } } else { Write-Host "No uvicorn log found at $outLog" }

Write-Host "Background uvicorn start attempted. Check $outLog for more details."
