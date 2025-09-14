# Stops uvicorn processes, starts uvicorn, waits for it to become healthy, then POSTs an emulator payload
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "Stopping existing uvicorn processes (if any)..."
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -match 'uvicorn' }
if ($procs) {
    foreach ($p in $procs) {
        Write-Host "Stopping PID" $p.ProcessId
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "No uvicorn process found"
}

# Start uvicorn detached and capture PID
$python = Join-Path -Path (Get-Location) -ChildPath ".\venv\Scripts\python.exe"
if (-Not (Test-Path $python)) {
    Write-Host "Python executable not found at $python"; exit 2
}

$args = @('-m','uvicorn','leantrader.api.app:app','--reload')
Write-Host "Starting uvicorn via: $python $($args -join ' ')"
$proc = Start-Process -FilePath $python -ArgumentList $args -NoNewWindow -WindowStyle Hidden -PassThru
Write-Host "Started uvicorn PID=$($proc.Id)"

# Wait for health
$healthUrl = 'http://127.0.0.1:8000/healthz'
$max = 30
$ok = $false
for ($i=0; $i -lt $max; $i++) {
    try {
        $r = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch {
        Start-Sleep -Seconds 1
    }
}
if ($ok) { Write-Host "Health OK" } else { Write-Host "Health check failed or timed out" }

# Run emulator trade payload
$callback = 'http://127.0.0.1:8000/telegram/callback'
$payload = @{ data = '{"action":"trade","side":"buy","pair":"XAUUSD","price":2350.00,"qty":1}' }
$body = $payload | ConvertTo-Json
try {
    $resp = Invoke-WebRequest -Uri $callback -Method POST -Body $body -ContentType 'application/json' -UseBasicParsing -TimeoutSec 5
    Write-Host "Emulator response status:" $resp.StatusCode
    Write-Host $resp.Content
} catch {
    Write-Host "Emulator POST failed:" $_.Exception.Message
}

# Quick import sanity check
try {
    & $python -c "import importlib; m=importlib.import_module('leantrader'); print('leantrader import OK, file=' + getattr(m,'__file__','<pkg>'))"
} catch {
    Write-Host "Import check failed"
}

Write-Host "Script finished. Uvicorn PID=$($proc.Id)"
