<# 
 Safe-merge LeanTrader bundle into the current repo.
 - Source: .\_incoming\bundle      (created by Expand-Archive)
 - Dest:   .\                      (repo root)
 - Will NOT overwrite existing files; writes *.incoming instead.
 - Skips common junk (venvs, pyc, logs).
#>

param(
  [string]$Source = "_incoming\bundle",
  [string]$Dest   = ".",
  [switch]$DryRun # if set, only prints what would happen
)

function Ensure-Dir([string]$Path) {
  if (-not (Test-Path $Path)) {
    New-Item -ItemType Directory -Path $Path | Out-Null
  }
}

function Copy-Safe([string]$From, [string]$To, [switch]$DryRun) {
  $toDir = Split-Path -Parent $To
  Ensure-Dir $toDir

  if (Test-Path $To) {
    $incoming = "$To.incoming"
    if ($DryRun) {
      Write-Host "[DRY] conflict -> $incoming" -ForegroundColor Yellow
    } else {
      Copy-Item -Path $From -Destination $incoming -Force
      Write-Host "[OK ] conflict -> $incoming" -ForegroundColor Yellow
    }
  } else {
    if ($DryRun) {
      Write-Host "[DRY] copy     -> $To" -ForegroundColor DarkGray
    } else {
      Copy-Item -Path $From -Destination $To -Force
      Write-Host "[OK ] copy     -> $To" -ForegroundColor Green
    }
  }
}

# --- Guard: make sure source exists ---
if (-not (Test-Path $Source)) {
  Write-Error "Source folder '$Source' not found. Did you run Expand-Archive correctly?"
  exit 1
}

# --- Ignore patterns (skip these from the bundle) ---
$skipPatterns = @(
  '^\.venv($|\\)',
  '^env($|\\)',
  '^__pycache__($|\\)',
  '\.pyc$',
  '^\.git($|\\)',
  '^logs($|\\)',
  '^runtime($|\\)',
  '^\.pytest_cache($|\\)',
  '^\.ruff_cache($|\\)'
)

# Normalize paths
$srcRoot = (Resolve-Path $Source).Path
$dstRoot = (Resolve-Path $Dest).Path

Write-Host "Merging from '$srcRoot' -> '$dstRoot'" -ForegroundColor Cyan
if ($DryRun) { Write-Host "Running in DRY-RUN mode" -ForegroundColor DarkYellow }

# Walk the source tree
$files = Get-ChildItem -Path $srcRoot -Recurse -File
foreach ($f in $files) {
  $rel = $f.FullName.Substring($srcRoot.Length).TrimStart('\','/')
  # apply skip filters
  $skip = $false
  foreach ($rx in $skipPatterns) {
    if ($rel -match $rx) { $skip = $true; break }
  }
  if ($skip) { continue }

  $target = Join-Path $dstRoot $rel
  Copy-Safe -From $f.FullName -To $target -DryRun:$DryRun
}

Write-Host "Done. Search for '*.incoming' to review conflicts." -ForegroundColor Cyan
