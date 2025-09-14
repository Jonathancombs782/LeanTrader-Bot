# Merge nested duplicate src/leantrader/src/leantrader into src/leantrader
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repo = (Get-Location).Path
$nested = Join-Path $repo 'src\leantrader\src\leantrader'
$top = Join-Path $repo 'src\leantrader'
if (-Not (Test-Path $nested)) { Write-Host "No nested duplicate found at $nested"; exit 0 }

$ts = (Get-Date).ToString('yyyyMMdd_HHmmss')
$backup = Join-Path $repo "runtime\backups\merge_nested_$ts"
New-Item -ItemType Directory -Path $backup -Force | Out-Null

Write-Host "Merging nested duplicate from:`n  $nested`ninto:`n  $top`nBackups -> $backup"`n
function Merge-Item($srcPath, $dstPath) {
    if ((Test-Path $srcPath) -and -not (Test-Path $dstPath)) {
        Write-Host "MOVE (new) -> $dstPath"
        Move-Item -LiteralPath $srcPath -Destination $dstPath -Force
        return
    }
    if ((Test-Path $srcPath) -and (Test-Path $dstPath)) {
        $srcIsDir = (Get-Item $srcPath).PSIsContainer
        $dstIsDir = (Get-Item $dstPath).PSIsContainer
        if ($srcIsDir -and $dstIsDir) {
            # Recurse
            Get-ChildItem -LiteralPath $srcPath -Force | ForEach-Object {
                $childSrc = $_.FullName
                $childRel = Resolve-Path $childSrc | Select-Object -ExpandProperty Path
                $rel = $childSrc.Substring($srcPath.Length).TrimStart('\')
                $childDst = Join-Path $dstPath $rel
                $childDstDir = Split-Path $childDst -Parent
                if (-not (Test-Path $childDstDir)) { New-Item -ItemType Directory -Path $childDstDir -Force | Out-Null }
                Merge-Item $childSrc $childDst
            }
            # After merging children, remove the empty source dir
            try { Remove-Item -LiteralPath $srcPath -Force -Recurse -ErrorAction SilentlyContinue } catch {}
            return
        }
        if (-not $srcIsDir -and -not $dstIsDir) {
            # Both files - compare content
            $hashSrc = Get-FileHash -Algorithm SHA256 -Path $srcPath
            $hashDst = Get-FileHash -Algorithm SHA256 -Path $dstPath
            if ($hashSrc.Hash -ne $hashDst.Hash) {
                # backup dst then overwrite
                $rel = $dstPath.Substring($top.Length).TrimStart('\')
                $bpath = Join-Path $backup $rel
                $bdir = Split-Path $bpath -Parent
                if (-not (Test-Path $bdir)) { New-Item -ItemType Directory -Path $bdir -Force | Out-Null }
                Copy-Item -LiteralPath $dstPath -Destination $bpath -Force
                Write-Host "OVERWRITE (changed) -> $dstPath (backup -> $bpath)"
                Copy-Item -LiteralPath $srcPath -Destination $dstPath -Force
                Remove-Item -LiteralPath $srcPath -Force -ErrorAction SilentlyContinue
            } else {
                # identical, remove src
                Write-Host "SKIP identical -> $dstPath"
                Remove-Item -LiteralPath $srcPath -Force -ErrorAction SilentlyContinue
            }
            return
        }
        # If types differ, back up dst and move src over
        $rel = $dstPath.Substring($top.Length).TrimStart('\')
        $bpath = Join-Path $backup $rel
        $bdir = Split-Path $bpath -Parent
        if (-not (Test-Path $bdir)) { New-Item -ItemType Directory -Path $bdir -Force | Out-Null }
        if (Test-Path $dstPath) { Copy-Item -LiteralPath $dstPath -Destination $bpath -Recurse -Force }
        Write-Host "REPLACE (type change) -> $dstPath (backup -> $bpath)"
        Remove-Item -LiteralPath $dstPath -Recurse -Force -ErrorAction SilentlyContinue
        Move-Item -LiteralPath $srcPath -Destination $dstPath -Force
        return
    }
}

# Iterate top-level children in nested
Get-ChildItem -LiteralPath $nested -Force | ForEach-Object {
    $src = $_.FullName
    $name = $_.Name
    $dst = Join-Path $top $name
    Merge-Item $src $dst
}

# Remove leftover parent src folder if empty
$parent = Join-Path $repo 'src\leantrader\src'
if (Test-Path $parent) {
    try { Remove-Item -LiteralPath $parent -Recurse -Force -ErrorAction SilentlyContinue; Write-Host "Removed parent $parent" } catch { Write-Host "Could not remove parent $parent" }
}

Write-Host "Merge complete. Backups written to: $backup"
Write-Host 'Final src\leantrader listing:'
Get-ChildItem -Path $top -Force | ForEach-Object { Write-Host $_.Name }
