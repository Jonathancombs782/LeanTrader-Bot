# Safe PowerShell scheduler script for the opt-in pipeline
# This registers a scheduled task to run the pipeline every hour when ENABLE_LEARNING is required.
param(
    [string]$TaskName = 'LeanTrader_Pipeline'
)

# Prefer repo venv python if present; fallback to python in PATH
$python = "$PWD\.venv\\Scripts\\python.exe"
if (-not (Test-Path $python)) { $python = 'python' }

$cmd = "$env:ENABLE_LEARNING='true'; & `"$python`" `"$PWD\\tools\\pipeline.py`""
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ("-NoProfile -WindowStyle Hidden -Command " + $cmd)
$trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(2)) -RepetitionInterval (New-TimeSpan -Minutes 60) -RepetitionDuration ([TimeSpan]::MaxValue)
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -RunLevel Highest
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Force
Write-Output "Scheduled task '$TaskName' registered to run hourly (opt-in)."
