$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $here

if (Test-Path ".venv\Scripts\Activate.ps1") {
    & powershell -NoProfile -ExecutionPolicy Bypass -Command ". .\.venv\Scripts\Activate.ps1; python tools\auto_static_runner.py"
} else {
    python tools\auto_static_runner.py
}

Pop-Location
Pop-Location
