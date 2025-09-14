<#
Safely back up the nested duplicate package tree:
- source: src\leantrader\src\leantrader
- backup: runtime\backups\nested_backup_<ts>.zip
- action: compress then remove nested tree
- produces: runtime\merge_report.txt

Run: powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\remove_nested_and_backup.ps1
#>

param(
    [switch]$WhatIf
)

function Write-Report($lines) {
    $outDir = "runtime"
    if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
    $reportFile = Join-Path $outDir 'merge_report.txt'
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $header = "Merge report generated: $timestamp"
    $content = $header + "`n`n" + ($lines -join "`n")
    $content | Out-File -FilePath $reportFile -Encoding UTF8
    Write-Host "WROTE_REPORT: $reportFile"
}

$nestedRel = 'src\leantrader\src\leantrader'
$nested = Join-Path (Get-Location) $nestedRel
$lines = @()

if (-not (Test-Path $nested)) {
    $lines += "NO_NESTED_FOUND: $nestedRel"
    Write-Report $lines
    exit 0
}

$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupDir = Join-Path (Join-Path (Get-Location) 'runtime') 'backups'
if (-not (Test-Path $backupDir)) { New-Item -ItemType Directory -Path $backupDir -Force | Out-Null }

$zipName = "nested_backup_$ts.zip"
$zipPath = Join-Path $backupDir $zipName

try {
    Write-Host "CREATING_ZIP: $zipPath"
    if ($WhatIf) { Write-Host "WhatIf: would Compress-Archive -Path $nested -DestinationPath $zipPath -Force"; $lines += "WHATIF_CREATED_ZIP:$zipPath"; Write-Report $lines; exit 0 }

    # Use Compress-Archive which can accept a folder path; ensure no open handles
    Compress-Archive -Path $nested -DestinationPath $zipPath -Force
    $lines += "ZIP_CREATED: $zipPath"

    # Verify zip exists
    if (-not (Test-Path $zipPath)) { throw "Zip creation failed: $zipPath not found" }

    # Remove the nested tree
    Write-Host "REMOVING_NESTED: $nestedRel"
    Remove-Item -LiteralPath $nested -Recurse -Force
    # Remove the now-empty parent 'src\leantrader\src' if it exists
    $parent = Join-Path (Join-Path (Get-Location) 'src\leantrader') 'src'
    if (Test-Path $parent) {
        Remove-Item -LiteralPath $parent -Recurse -Force -ErrorAction SilentlyContinue
        $lines += "REMOVED_PARENT_SRC: $parent"
    }

    $lines += "REMOVED_NESTED: $nestedRel"
    $lines += "BACKUP_LOCATION: $zipPath"
    Write-Report $lines
    Write-Host "DONE"
} catch {
    $err = $_.Exception.Message
    Write-Host "ERROR: $err"
    $lines += "ERROR: $err"
    Write-Report $lines
    exit 1
}
