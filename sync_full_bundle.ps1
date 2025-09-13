<#
Sync ALL content from _incoming\bundle into the repo:
- Package modules -> .\src\leantrader
- Top-level files  -> repo root (pyproject.toml, .env.example, Dockerfile, etc.)
- Deploy folder    -> .\deploy
- Data stubs       -> .\data
Never overwrite: conflicting targets become *.incoming
#>

param(
  [string]$Bundle = "_incoming\bundle"
)

function Ensure-Dir([string]$p) { if (-not (Test-Path $p)) { New-Item -ItemType Directory -Path $p | Out-Null } }

function Copy-Safe([string]$From, [string]$To) {
  Ensure-Dir (Split-Path -Parent $To)
  if (Test-Path $To) {
    Copy-Item $From "$To.incoming" -Recurse -Force
    Write-Host "[CONFLICT] -> $To.incoming" -ForegroundColor Yellow
  } else {
    Copy-Item $From $To -Recurse -Force
    Write-Host "[OK]       -> $To" -ForegroundColor Green
  }
}

# --- Guards ---
if (-not (Test-Path $Bundle)) { Write-Error "Bundle '$Bundle' not found"; exit 1 }

# --- Ensure main layout at repo root ---
Ensure-Dir ".\src"
Ensure-Dir ".\src\leantrader"
Ensure-Dir ".\deploy"
Ensure-Dir ".\data"

# 1) Copy the entire Python package from bundle/leantrader/* -> src/leantrader/*
$pkgSrc = Join-Path $Bundle "leantrader"
if (Test-Path $pkgSrc) {
  Get-ChildItem $pkgSrc -Force | ForEach-Object {
    Copy-Safe -From $_.FullName -To (Join-Path ".\src\leantrader" $_.Name)
  }
} else {
  Write-Host "WARN: $pkgSrc not found in bundle" -ForegroundColor DarkYellow
}

# 2) Copy deploy stack (nginx, docker-compose, etc.)
$depSrc = Join-Path $Bundle "deploy"
if (Test-Path $depSrc) {
  Get-ChildItem $depSrc -Force | ForEach-Object {
    Copy-Safe -From $_.FullName -To (Join-Path ".\deploy" $_.Name)
  }
}

# 3) Copy data stubs (ohlc, telegram premium list, etc.)
$dataSrc = Join-Path $Bundle "data"
if (Test-Path $dataSrc) {
  Get-ChildItem $dataSrc -Force | ForEach-Object {
    Copy-Safe -From $_.FullName -To (Join-Path ".\data" $_.Name)
  }
}

# 4) Copy top-level files at repo root
$rootFiles = @("pyproject.toml",".env.example","Dockerfile","README.md")
foreach ($f in $rootFiles) {
  $src = Join-Path $Bundle $f
  if (Test-Path $src) { Copy-Safe -From $src -To (Join-Path "." $f) }
}

Write-Host "Done. Review any '*.incoming' files and merge as needed." -ForegroundColor Cyan
