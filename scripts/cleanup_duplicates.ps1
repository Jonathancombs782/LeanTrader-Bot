<#
Backup and remove duplicate source trees that confuse IDE analysis:
- Back up to runtime\backups\duplicates_<ts>.zip
- Remove top-level 'leantrader' folder and '_incoming/bundle/leantrader' trees
- Remove stray pyproject.toml files under those trees (root pyproject kept)

Run: powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\cleanup_duplicates.ps1
#>

$ErrorActionPreference = 'Stop'
$root = Get-Location
$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupDir = Join-Path $root 'runtime\backups'
if (-not (Test-Path $backupDir)) { New-Item -ItemType Directory -Path $backupDir -Force | Out-Null }
$zip = Join-Path $backupDir ("duplicates_$ts.zip")

$targets = @()
$t1 = Join-Path $root 'leantrader'
if (Test-Path $t1) { $targets += $t1 }
$t2 = Join-Path $root '_incoming\bundle\leantrader'
if (Test-Path $t2) { $targets += $t2 }

if ($targets.Count -eq 0) {
    Write-Host 'NO_DUPLICATE_TREES_FOUND'
    exit 0
}

Write-Host "ZIPPING_DUPLICATES: $zip"
Compress-Archive -Path $targets -DestinationPath $zip -Force

foreach ($t in $targets) {
    Write-Host "REMOVING: $t"
    Remove-Item -LiteralPath $t -Recurse -Force
}

# Remove stray pyproject.toml under removed trees if any residue left
Get-ChildItem -Path $root -Recurse -Filter 'pyproject.toml' | Where-Object {
    $_.FullName -like (Join-Path $root 'leantrader*') -or $_.FullName -like (Join-Path $root '_incoming*')
} | ForEach-Object {
    try { Remove-Item -LiteralPath $_.FullName -Force } catch {}
}

Write-Host "DONE: BACKUP=$zip"
