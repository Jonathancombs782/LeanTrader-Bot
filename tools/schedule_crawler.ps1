# Safe PowerShell scheduler script for the opt-in crawler
# Registers a scheduled task to run the crawler continuously (restart on login/boot)
param(
    [string]$TaskName = 'LeanTrader_Crawler'
)

$python = "$PWD\.venv\\Scripts\\python.exe"
if (-not (Test-Path $python)) {
  $python = 'python'
}

# Build command: ensure ENABLE_CRAWL and seeds are honored by tools/web_crawler.py
$cmd = "$env:ENABLE_CRAWL='true'; & `"$python`" `"$PWD\\tools\\web_crawler.py`""
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ("-NoProfile -WindowStyle Hidden -Command " + $cmd)

# Trigger: at logon, and restart every 60 minutes if it exits
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -RestartCount 9999 -RestartInterval (New-TimeSpan -Minutes 60)
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -RunLevel Highest

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
Write-Output "Scheduled task '$TaskName' registered (starts at logon, restarts if it exits)."
