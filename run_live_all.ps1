# run_live_all.ps1
param(
  [string]$PY = "python",
  [string]$TIMEFRAME = "1m"
)

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $here
& .\.venv\Scripts\Activate.ps1

# panel 1: Crypto (use Kraken while BinanceUS keys/geo are pending)
wt -w 0 new-tab PowerShell -NoExit -Command `
  "$PY -u run_live.py --exchange kraken --symbols 'BTC/USD,ETH/USD,DOGE/USD' --timeframe $TIMEFRAME --balance_every 0"

# panel 2: Meme
wt -w 0 split-pane -H PowerShell -NoExit -Command `
  "$PY -u run_live_meme.py --exchange kraken --timeframe $TIMEFRAME --stake_usd 2 --balance_every 0"

# panel 3: FX via MT5 (after mt5_smoke/env are set)
wt -w 0 split-pane -V PowerShell -NoExit -Command `
  "$PY -u run_live_fx.py --pairs 'EURUSD,GBPUSD,XAUUSD' --timeframe 5m --lots 0.02 --balance_every 30"

Pop-Location
