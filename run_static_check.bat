@echo off
setlocal
set ROOT=%~dp0
cd /d "%ROOT%"

if exist ".venv\Scripts\Activate.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "& '.\.venv\Scripts\Activate.ps1'; python tools\auto_static_runner.py"
) else (
    python tools\auto_static_runner.py
)

endlocal
endlocal
