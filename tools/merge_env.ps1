param(
    [string]$EnvPath = ".env",
    [string]$RecoverPath = ".env.recover",
    [switch]$DryRun
)

# Merge missing keys from .env.recover into .env without overwriting existing values
# Usage: ./tools/merge_env.ps1 -EnvPath .env -RecoverPath .env.recover

if (!(Test-Path $RecoverPath)) { Write-Error "Recover file not found: $RecoverPath"; exit 1 }
if (!(Test-Path $EnvPath)) { New-Item -ItemType File -Path $EnvPath -Force | Out-Null }

$envLines = Get-Content -Raw -Path $EnvPath -ErrorAction SilentlyContinue
$recoverLines = Get-Content -Raw -Path $RecoverPath

# Build existing key set (ignore comments and blanks)
$existing = @{}
foreach ($line in ($envLines -split "`n")) {
    if ($line -match '^[\s#]') { continue }
    if ($line -match '^([^=]+)=') { $k=$Matches[1].Trim(); if ($k) { $existing[$k]=$true } }
}

# Gather missing entries preserving comments/sections but only for key lines not present
$toAppend = New-Object System.Collections.Generic.List[string]
foreach ($line in ($recoverLines -split "`n")) {
    if ($line -match '^[\s#]') {
        # keep section/comment headers if they precede at least one missing key
        $toAppend.Add($line)
        continue
    }
    if ($line -match '^([^=]+)=(.*)$') {
        $k=$Matches[1].Trim()
        if (-not $existing.ContainsKey($k)) {
            $toAppend.Add($line)
        } else {
            # If header/comment just added with no following missing keys, remove trailing comments later
        }
    }
}

# Clean trailing comment blocks with no following key
$cleaned = New-Object System.Collections.Generic.List[string]
$pendingComments = New-Object System.Collections.Generic.List[string]
foreach ($line in $toAppend) {
    if ($line -match '^[\s#]') { $pendingComments.Add($line); continue }
    if ($pendingComments.Count -gt 0) { $cleaned.AddRange($pendingComments); $pendingComments.Clear() }
    $cleaned.Add($line)
}

if ($DryRun) {
    Write-Host "Would append the following lines:" -ForegroundColor Cyan
    $cleaned | ForEach-Object { Write-Host $_ }
    exit 0
}

if ($cleaned.Count -gt 0) {
    Add-Content -Path $EnvPath -Value "`n# --- merged from .env.recover on $(Get-Date -Format o) ---"
    $cleaned | ForEach-Object { Add-Content -Path $EnvPath -Value $_ }
    Write-Host "Merged $($cleaned.Count) lines into $EnvPath" -ForegroundColor Green
} else {
    Write-Host "No missing keys to merge." -ForegroundColor Yellow
}
