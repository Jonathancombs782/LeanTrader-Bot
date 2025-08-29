@echo off
setlocal
set HERE=%~dp0
cd /d "%HERE%"

REM activate venv in each window automatically
set ACT=.\\.venv\\Scripts\\Activate.ps1

REM You can edit these defaults
set TF=1m
set FXTF=5m
set STAKE=2
set LOTS=0.02
set NEWSTOP=3
set BALMIN=60

REM Pre-harvest news (optional)
powershell -NoLogo -ExecutionPolicy Bypass -Command "cd '%HERE%'; & %ACT%; python news_harvest.py"

REM Crypto
start "Crypto" powershell -NoExit -ExecutionPolicy Bypass -Command "cd '%HERE%'; & %ACT%; python -u run_live.py --symbols 'BTC/USDT,ETH/USDT' --timeframe %TF% --stake_usd %STAKE% --news_top %NEWSTOP% --balance_every %BALMIN%"

REM Meme
start "Meme" powershell -NoExit -ExecutionPolicy Bypass -Command "cd '%HERE%'; & %ACT%; python -u run_live_meme.py --symbols 'DOGE/USDT,PEPE/USDT,SHIB/USDT' --timeframe %TF% --stake_usd %STAKE% --news_top %NEWSTOP% --balance_every %BALMIN%"

REM FX
start "FX" powershell -NoExit -ExecutionPolicy Bypass -Command "cd '%HERE%'; & %ACT%; python -u run_live_fx.py --pairs 'EURUSD,GBPUSD,XAUUSD' --timeframe %FXTF% --lots %LOTS% --stake_usd %STAKE% --news_top %NEWSTOP% --balance_every %BALMIN%"
endlocal
