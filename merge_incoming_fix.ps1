<#
Auto-merge '*.incoming' artifacts produced by sync_full_bundle.ps1 into final tree.
Policy:
- If target path missing -> move incoming into place.
- If target exists and identical -> delete incoming.
- If target exists and differs -> backup existing to *.backup.TIMESTAMP and replace with incoming (incoming wins).
- Backups kept under ./runtime/backups for safety.
Run from repo root: powershell -ExecutionPolicy Bypass -File .\merge_incoming_fix.ps1
#>

$Root = Get-Location
$BackupDir = Join-Path $Root.Path "runtime\backups\incoming_merge"
if (-not (Test-Path $BackupDir)) { New-Item -ItemType Directory -Path $BackupDir | Out-Null }

function HashFile($path){ if (-not (Test-Path $path)) { return $null } ; return (Get-FileHash -Algorithm SHA256 -Path $path).Hash }

function Merge-Item($incomingPath){
    # incomingPath may be file or dir ending with .incoming
    $isDir = Test-Path $incomingPath -PathType Container
    $target = $incomingPath -replace '\.incoming$',''

    if (-not (Test-Path $target)){
        # safe move
        Write-Host "[MOVE] $incomingPath -> $target"
        Rename-Item -Path $incomingPath -NewName $target
        return
    }

    if ($isDir){
        # for each child in incoming, merge recursively
        Get-ChildItem -LiteralPath $incomingPath -Force | ForEach-Object {
            $childIn = $_.FullName
            $rel = $childIn.Substring($incomingPath.Length).TrimStart('\\')
            $childTarget = Join-Path $target $rel
            if ($_.PSIsContainer){
                if (-not (Test-Path $childTarget)){
                    New-Item -ItemType Directory -Path $childTarget | Out-Null
                }
                # recurse into directory
                Merge-Directory $_.FullName $childTarget
            } else {
                Merge-File $_.FullName $childTarget
            }
        }
        # remove incoming dir if empty
        try{ Remove-Item -LiteralPath $incomingPath -Recurse -Force } catch {}
    } else {
        # file incoming, target exists -> compare
        Merge-File $incomingPath $target
    }
}

function Merge-Directory($incDir, $tgtDir){
    Get-ChildItem -LiteralPath $incDir -Force | ForEach-Object {
        $childIn = $_.FullName
        $rel = $childIn.Substring($incDir.Length).TrimStart('\\')
        $childTarget = Join-Path $tgtDir $rel
        if ($_.PSIsContainer){
            if (-not (Test-Path $childTarget)) { New-Item -ItemType Directory -Path $childTarget | Out-Null }
            Merge-Directory $_.FullName $childTarget
        } else {
            Merge-File $_.FullName $childTarget
        }
    }
    # remove incoming dir if empty
    try{ Remove-Item -LiteralPath $incDir -Recurse -Force } catch {}
}

function Merge-File($incFile, $tgtFile){
    if (-not (Test-Path $tgtFile)){
        $parent = Split-Path -Parent $tgtFile
        if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
        Write-Host "[MOVE-FILE] $incFile -> $tgtFile"
        Move-Item -LiteralPath $incFile -Destination $tgtFile -Force
        return
    }
    # both exist: compare hash
    $h1 = HashFile $incFile
    $h2 = HashFile $tgtFile
    if ($h1 -eq $h2){
        Write-Host "[IDENTICAL] removing incoming $incFile"
        Remove-Item -LiteralPath $incFile -Force
        return
    }
    # different: backup target and overwrite with incoming
    $ts = Get-Date -Format "yyyyMMddHHmmss"
    $relTarget = $tgtFile -replace '[:\\]','_'
    $bak = Join-Path $BackupDir (Split-Path -Leaf $relTarget + ".backup.$ts")
    Write-Host "[CONFLICT] backing up $tgtFile -> $bak and replacing with incoming" -ForegroundColor Yellow
    Copy-Item -LiteralPath $tgtFile -Destination $bak -Force
    # overwrite target
    Copy-Item -LiteralPath $incFile -Destination $tgtFile -Force
    Remove-Item -LiteralPath $incFile -Force
}

# Find all *.incoming entries under src and root
$incomingItems = Get-ChildItem -Recurse -Force -Filter "*.incoming" | Sort-Object FullName
if (-not $incomingItems){ Write-Host "No *.incoming items found, nothing to merge."; exit 0 }

Write-Host "Found $($incomingItems.Count) incoming items. Processing..."
foreach ($it in $incomingItems){
    Merge-Item $it.FullName
}

Write-Host "Merge complete. Backups in: $BackupDir" -ForegroundColor Cyan
