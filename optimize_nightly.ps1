# optimize_nightly.ps1
param(
  [string]$Exchange = "binanceus",
  [string]$Symbols  = "DOGE/USD,BTC/USD",
  [string]$Timeframe = "1m",
  [int]$Trials = 40,
  [int]$LookbackDays = 60
)

$ErrorActionPreference = "Stop"

# Compute rolling dates (UTC)
$end = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd")
$start = (Get-Date).AddDays(-$LookbackDays).ToUniversalTime().ToString("yyyy-MM-dd")

Write-Host "Running ingest_calendar..."
python - <<'PYCODE'
import subprocess, sys
subprocess.run([sys.executable, "ingest_calendar.py"], check=False)
PYCODE

Write-Host "Running research_optuna from $start to $end ..."
& .\.venv\Scripts\python.exe "research_optuna.py" --exchange $Exchange --symbols $Symbols --timeframe $Timeframe --start $start --end $end --trials $Trials
Write-Host "Optimization complete."
