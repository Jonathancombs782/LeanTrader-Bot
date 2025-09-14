# Move nested duplicate package tree src/leantrader/src/leantrader -> runtime/backups/duplicate_nested_leantrader_TIMESTAMP
param(
    [string]$RepoRoot = (Get-Location).Path
)

$nested = Join-Path $RepoRoot 'src\leantrader\src\leantrader'
if (-Not (Test-Path $nested)) { Write-Host "No nested duplicate found at $nested"; exit 0 }

$ts = (Get-Date).ToString('yyyyMMdd_HHmmss')
$backupDir = Join-Path $RepoRoot "runtime\backups\duplicate_nested_leantrader_$ts"
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

Write-Host "Moving nested duplicate $nested -> $backupDir"
Move-Item -Path $nested -Destination $backupDir -Force

# If the empty parent src exists (src/leantrader/src), remove it
$parent = Join-Path $RepoRoot 'src\leantrader\src'
if (Test-Path $parent) {
    try { Remove-Item -LiteralPath $parent -Recurse -Force -ErrorAction Stop; Write-Host "Removed empty parent $parent" } catch { Write-Host "Parent $parent not empty or removal failed: $_" }
}

Write-Host "Duplicate nested package moved to $backupDir"
