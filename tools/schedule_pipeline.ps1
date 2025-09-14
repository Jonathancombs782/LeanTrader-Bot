# Safe PowerShell scheduler script for the opt-in pipeline
# This registers a scheduled task to run the pipeline every hour when ENABLE_LEARNING is required.
param(
    [string]$TaskName = 'LeanTrader_Pipeline'
)
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -WindowStyle Hidden -Command `"$env:VIRTUAL_ENV_ACTIVATE=''; $env:ENABLE_LEARNING='true'; python '$PWD\\tools\\pipeline.py'`""
$trigger = New-ScheduledTaskTrigger -Daily -At (Get-Date).Date.AddHours((Get-Date).Hour + 1) -RepetitionInterval (New-TimeSpan -Minutes 60) -RepetitionDuration ([TimeSpan]::MaxValue)
$principal = New-ScheduledTaskPrincipal -UserId "NT AUTHORITY\SYSTEM" -RunLevel Highest
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Force
Write-Output "Scheduled task '$TaskName' registered to run hourly (opt-in)."
