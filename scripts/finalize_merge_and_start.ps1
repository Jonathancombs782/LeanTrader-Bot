<#
Finalizer script: merges nested duplicate package into canonical tree, backs up overwritten files,
removes duplicate folders, starts uvicorn in background, and writes a merge report.
Run from repo root in PowerShell (no elevated required normally):

powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\finalize_merge_and_start.ps1

This will create logs under runtime/merge_and_start.log and runtime/uvicorn.log and backups under runtime/backups.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repo = (Get-Location).Path
$reportFile = Join-Path $repo 'runtime\merge_report.txt'
$mergeLog = Join-Path $repo 'runtime\merge_and_start.log'
Start-Transcript -Path $mergeLog -Force | Out-Null

function Write-Report($msg) { Add-Content -Path $reportFile -Value $msg }

Write-Host "FINALIZE MERGE & START - Beginning at $(Get-Date)"
Write-Report "FINALIZE MERGE & START - Run at $(Get-Date)"

$nested = Join-Path $repo 'src\leantrader\src\leantrader'
$top = Join-Path $repo 'src\leantrader'
if (-Not (Test-Path $top)) { Write-Host "ERROR: Top-level package not found at $top"; Write-Report "ERROR: Top-level package not found at $top"; Stop-Transcript; exit 2 }

if (-Not (Test-Path $nested)) {
    Write-Host "No nested duplicate found at $nested - nothing to merge"
    Write-Report "No nested duplicate found at $nested"
} else {
    $ts = (Get-Date).ToString('yyyyMMdd_HHmmss')
    $backup = Join-Path $repo ("runtime\backups\merge_final_$ts")
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    Write-Host "Backup directory: $backup"
    Write-Report "Backup directory: $backup"

    # Copy nested into backup for safe keeping
    Write-Host "Copying nested duplicate to backup (preserve full copy)..."
    Copy-Item -Path $nested -Destination $backup -Recurse -Force
    Write-Report "Copied nested duplicate to $backup"

    # For each child in nested: if new -> move, if exists and dir->robocopy merge, if file->compare and backup/overwrite or remove if identical
    $moved=0; $backed=0; $removedIdentical=0; $replaced=0
    $children = Get-ChildItem -LiteralPath $nested -Force
    foreach ($child in $children) {
        $src = $child.FullName
        $name = $child.Name
        $dst = Join-Path $top $name
        if (-Not (Test-Path $dst)) {
            Write-Host "MOVE_NEW: $name"
            Move-Item -LiteralPath $src -Destination $dst -Force
            Write-Report "MOVE_NEW: $name -> $dst"
            $moved++
            continue
        }

        if ((Get-Item $src).PSIsContainer -and (Get-Item $dst).PSIsContainer) {
            Write-Host "MERGE_DIR: $name (robocopy)"
            Write-Report "MERGE_DIR: $name -> robocopy $src -> $dst"
            # Mirror src into dst using robocopy. /E to copy subdirs, /FFT for timestamp tolerance
            robocopy $src $dst /MIR /FFT /NFL /NDL /NJH /NJS | Out-Null
            Remove-Item -LiteralPath $src -Recurse -Force -ErrorAction SilentlyContinue
            $moved++
            continue
        }

        if (-not (Get-Item $src).PSIsContainer -and -not (Get-Item $dst).PSIsContainer) {
            $hSrc = (Get-FileHash -Algorithm SHA256 -Path $src).Hash
            $hDst = (Get-FileHash -Algorithm SHA256 -Path $dst).Hash
            if ($hSrc -ne $hDst) {
                $bpath = Join-Path $backup $name
                Copy-Item -Path $dst -Destination $bpath -Force
                Write-Host "BACKUP_OVERWRITE: $name -> backup: $bpath"
                Write-Report "BACKUP_OVERWRITE: $name -> $bpath"
                Copy-Item -Path $src -Destination $dst -Force
                Remove-Item -LiteralPath $src -Force -ErrorAction SilentlyContinue
                $backed++
                $replaced++
            } else {
                Write-Host "IDENTICAL_REMOVE_SRC: $name"
                Write-Report "IDENTICAL_REMOVE_SRC: $name"
                Remove-Item -LiteralPath $src -Force -ErrorAction SilentlyContinue
                $removedIdentical++
            }
            continue
        }

        # Fallback: replace dst with src
        $bpath = Join-Path $backup $name
        if (Test-Path $dst) { Copy-Item -Path $dst -Destination $bpath -Recurse -Force }
        Write-Host "REPLACE_OTHER: $name (backup -> $bpath)"
        Write-Report "REPLACE_OTHER: $name -> $bpath"
        Remove-Item -LiteralPath $dst -Recurse -Force -ErrorAction SilentlyContinue
        Move-Item -LiteralPath $src -Destination $dst -Force
        $moved++
    }

    # Remove nested parent if empty
    $parent = Join-Path $repo 'src\leantrader\src'
    if (Test-Path $parent) {
        try { Remove-Item -LiteralPath $parent -Recurse -Force -ErrorAction SilentlyContinue; Write-Host "Removed parent: $parent"; Write-Report "Removed parent: $parent" } catch { Write-Host "Could not remove parent: $parent"; Write-Report "Could not remove parent: $parent" }
    }

    Write-Host "Merge summary: moved=$moved, backed=$backed, removed_identical=$removedIdentical, replaced=$replaced"
    Write-Report "Merge summary: moved=$moved, backed=$backed, removed_identical=$removedIdentical, replaced=$replaced"
}

# At this point canonical tree should be the only active package under src/leantrader
Write-Host "Listing top-level src\leantrader entries:"; Get-ChildItem -Path $top -Force | ForEach-Object { Write-Host $_.Name }
Write-Report "Top-level src\leantrader listing written below"
Get-ChildItem -Path $top -Force | ForEach-Object { Write-Report $_.Name }

# Start uvicorn in background, log to runtime/uvicorn.log
$python = Join-Path $repo '.\venv\Scripts\python.exe'
$uvLog = Join-Path $repo 'runtime\uvicorn.log'
if (-not (Test-Path $python)) { Write-Host "Python executable not found at $python; skipping server start"; Write-Report "Python executable not found at $python; skipping server start" } else {
    Write-Host "Starting uvicorn background process; logs -> $uvLog"
    Write-Report "Starting uvicorn background process; logs -> $uvLog"
    $inner = "& '$python' -u -m uvicorn 'leantrader.api.app:app' --reload --host 127.0.0.1 --port 8000 > '$uvLog' 2>&1"
    Start-Process -FilePath 'powershell' -ArgumentList '-NoProfile','-WindowStyle','Hidden','-Command',$inner -PassThru | Out-Null
    Start-Sleep -Seconds 4
    if (Test-Path $uvLog) { Write-Host '---- uvicorn.log (tail 200) ----'; Get-Content -Path $uvLog -Tail 200 | ForEach-Object { Write-Host $_ } ; Write-Report 'uvicorn.log tail written' } else { Write-Host 'No uvicorn.log present (server may not have started)'; Write-Report 'No uvicorn.log present' }

    # Health check and emulator POST
    try { $r = Invoke-WebRequest -Uri http://127.0.0.1:8000/healthz -UseBasicParsing -TimeoutSec 5; Write-Host "Health status: $($r.StatusCode)"; Write-Report "Health status: $($r.StatusCode)" } catch { Write-Host "Health check failed: $($_.Exception.Message)"; Write-Report "Health check failed: $($_.Exception.Message)" }
    try { $payload = @{ data = '{"action":"trade","side":"buy","pair":"XAUUSD","price":2350.00,"qty":1}' } | ConvertTo-Json; $resp = Invoke-WebRequest -Uri http://127.0.0.1:8000/telegram/callback -Method POST -Body $payload -ContentType 'application/json' -UseBasicParsing -TimeoutSec 5; Write-Host "Emulator POST status: $($resp.StatusCode)"; Write-Host $resp.Content; Write-Report "Emulator POST status: $($resp.StatusCode)" } catch { Write-Host "Emulator POST failed: $($_.Exception.Message)"; Write-Report "Emulator POST failed: $($_.Exception.Message)" }
}

Write-Host "Finalization complete. See $reportFile and $mergeLog for details."
Write-Report "Finalization complete at $(Get-Date)"
Stop-Transcript | Out-Null
