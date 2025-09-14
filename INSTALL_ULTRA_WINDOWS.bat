@echo off
REM ============================================================================
REM ULTRA TRADING SYSTEM - WINDOWS INSTALLATION SCRIPT
REM ============================================================================
REM This script will install all Ultra System files to your project
REM ============================================================================

echo.
echo ============================================================================
echo                    ULTRA TRADING SYSTEM INSTALLER
echo ============================================================================
echo.

REM Check if we're in the right directory
if not exist "ultra_core.py" (
    echo ERROR: This doesn't appear to be the LeanTrader_ForexPack directory!
    echo Please run this script from your project root directory.
    echo Expected location: C:\Users\User\Downloads\LeanTrader_ForexPack
    echo.
    pause
    exit /b 1
)

echo [OK] Found project directory
echo.

REM Create backup
echo Creating backup of existing files...
set BACKUP_DIR=backup_%date:~-4%%date:~3,2%%date:~0,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set BACKUP_DIR=%BACKUP_DIR: =0%
mkdir %BACKUP_DIR% 2>nul

if exist ultra_scout.py (
    echo Backing up ultra_scout.py...
    copy ultra_scout.py %BACKUP_DIR%\ultra_scout.py >nul
)

echo [OK] Backup created in: %BACKUP_DIR%
echo.

REM Check if ultra_system_complete.zip exists
if not exist "ultra_system_complete.zip" (
    echo ERROR: ultra_system_complete.zip not found!
    echo Please download the file from the workspace first.
    echo.
    pause
    exit /b 1
)

echo Extracting Ultra System files...

REM Extract using PowerShell (works on all Windows versions)
powershell -Command "Expand-Archive -Path 'ultra_system_complete.zip' -DestinationPath '.' -Force"

if %errorlevel% neq 0 (
    echo ERROR: Failed to extract files!
    echo Trying alternative method...
    
    REM Try using tar (available on Windows 10+)
    tar -xf ultra_system_complete.zip 2>nul
    
    if %errorlevel% neq 0 (
        echo.
        echo ERROR: Could not extract files automatically.
        echo Please extract ultra_system_complete.zip manually.
        pause
        exit /b 1
    )
)

echo [OK] Files extracted successfully
echo.

REM Verify critical files
echo Verifying installation...
set MISSING=0

if not exist "ultra_launcher.py" (
    echo [MISSING] ultra_launcher.py
    set MISSING=1
)
if not exist "ultra_ml_pipeline.py" (
    echo [MISSING] ultra_ml_pipeline.py
    set MISSING=1
)
if not exist "ultra_god_mode.py" (
    echo [MISSING] ultra_god_mode.py
    set MISSING=1
)
if not exist "tools\ultra_trainer.py" (
    echo [MISSING] tools\ultra_trainer.py
    set MISSING=1
)
if not exist "tools\market_data.py" (
    echo [MISSING] tools\market_data.py
    set MISSING=1
)

if %MISSING%==1 (
    echo.
    echo ERROR: Some files are missing! Please check the extraction.
    pause
    exit /b 1
)

echo [OK] All critical files verified
echo.

REM Install Python dependencies
echo Installing Python dependencies...
echo.

pip install -r requirements_ultra.txt

if %errorlevel% neq 0 (
    echo.
    echo WARNING: Some dependencies might have failed to install.
    echo You may need to install them manually.
    echo.
)

echo.
echo ============================================================================
echo                    INSTALLATION COMPLETE!
echo ============================================================================
echo.
echo The Ultra Trading System has been successfully installed!
echo.
echo FILES INSTALLED:
echo   - ultra_launcher.py (Main entry point)
echo   - ultra_ml_pipeline.py (ML orchestrator)
echo   - ultra_god_mode.py (Quantum/Swarm features)
echo   - ultra_moon_spotter.py (Micro cap finder)
echo   - ultra_forex_master.py (Forex/Metals trading)
echo   - ultra_telegram_master.py (Telegram signals)
echo   - tools\ultra_trainer.py (Advanced ML trainer)
echo   - tools\market_data.py (Market data manager)
echo   - And more...
echo.
echo TO START THE SYSTEM:
echo.
echo   1. Paper Trading Mode:
echo      python ultra_launcher.py --mode paper --god-mode --moon-spotter --forex
echo.
echo   2. With Training:
echo      python ultra_launcher.py --mode paper --train --god-mode
echo.
echo   3. Live Trading (be careful!):
echo      python ultra_launcher.py --mode live --god-mode --moon-spotter --forex
echo.
echo   4. With Telegram Signals:
echo      First edit telegram_config.json with your bot token
echo      Then: python ultra_launcher.py --telegram --telegram-token YOUR_TOKEN
echo.
echo DOCUMENTATION:
echo   - README_ULTRA.md - Full system documentation
echo   - TELEGRAM_SETUP.md - Telegram setup guide
echo.
echo ============================================================================
echo.
pause