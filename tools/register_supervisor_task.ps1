param(
    [string]$TaskName = "LeanTraderSupervisor",
    [string]$RepoPath = "${PSScriptRoot}",
    [string]$PythonExe = "$env:USERPROFILE\Downloads\LeanTrader_ForexPack\.venv\Scripts\python.exe"
)

$action = New-ScheduledTaskAction -Execute $PythonExe -Argument "-u -m tools.supervisor"
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "NT AUTHORITY\SYSTEM" -RunLevel Highest

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Force
Write-Output "Registered scheduled task $TaskName to run supervisor at startup." 
