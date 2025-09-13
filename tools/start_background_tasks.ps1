# start_background_tasks.ps1
# Simple local loop to run crawler and learner periodically (development only)

$python = Join-Path -Path $PSScriptRoot -ChildPath "..\.venv\Scripts\python.exe"

while ($true) {
    Write-Host "Running crawler..."
    & $python (Join-Path $PSScriptRoot "run_crawler.py")
    Write-Host "Running learner..."
    & $python (Join-Path $PSScriptRoot "learner.py")
    Write-Host "Sleeping 10m..."
    Start-Sleep -Seconds 600
}
