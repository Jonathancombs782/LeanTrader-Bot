
# LeanTrader – ForexPack (OANDA, MetaTrader5, IBKR)

Adds **forex** support to LeanTrader with:
- Broker adapters: **OANDA** (REST/stream), **MetaTrader5** (terminal), **IBKR** (ib_insync).
- **Forex backtesting** using Yahoo Finance (`yfinance`) symbols (e.g., `EURUSD=X`).
- Live/paper runners reusing your existing **strategy, risk, and guardrails**.
- **Daemonization guide** so the bot runs while you're offline.

> ⚠️ No guaranteed profits. Use practice/demo accounts first. Start micro-size.

---

## Install
```bash
pip install -r requirements_fx.txt
```
On Windows for MetaTrader5, install the **MetaTrader 5 terminal** and log in to your broker; the Python `MetaTrader5` package attaches to it.

## Configure Keys
Copy `.env.example` → `.env` and set:

```env
# OANDA (practice strongly recommended)
OANDA_ACCOUNT_ID=YOUR_PRACTICE_ACCOUNT
OANDA_API_TOKEN=YOUR_TOKEN
***REDACTED***           # practice or live

# MetaTrader5
MT5_LOGIN=1234567
MT5_PASSWORD=YOUR_PASS
MT5_SERVER=YourBroker-Server

# IBKR (optional; TWS or IB Gateway must be running)
IB_HOST=127.0.0.1
IB_PORT=7497
IB_CLIENT_ID=1
```

Choose pairs in `config_fx.yml` (defaults below use majors).

---

## Backtest (Forex)
```bash
python backtest_fx.py --symbols "EURUSD,GBPUSD,USDJPY" --timeframe 15m --since 2024-01-01
```
Uses Yahoo Finance data (`EURUSD=X`). Outputs report to `./reports/`.

## Paper Trade (OANDA stream)
```bash
python paper_fx_oanda.py --timeframe 5m --pairs "EUR/USD,GBP/USD,USD/JPY"
```
Requires OANDA practice token.

## Live Trade (choose adapter)
```bash
# OANDA
python run_live_fx.py --adapter oanda --pairs "EUR/USD,GBP/USD,USD/JPY" --timeframe 5m

# MetaTrader5
python run_live_fx.py --adapter mt5 --pairs "EURUSD,GBPUSD,USDJPY" --timeframe 5m

# IBKR
python run_live_fx.py --adapter ibkr --pairs "EUR.USD,GBP.USD,USD.JPY" --timeframe 5m
```
Uses **guardrails** (cooldown, loss-streak, profit lock) + **ATR stops/trailing**. Sizing uses **fixed USD risk** per trade.

---

## Run While Offline (Daemon)
- **Linux/macOS**: use `tmux` or `screen`, or create a `systemd` service (see `daemonize.md`).
- **Windows**: run in a persistent PowerShell window or use `NSSM` to wrap the Python script as a service.

---

## Notes
- IBKR & MetaTrader5 require local apps running.
- Symbol formats differ per adapter (see each runner’s help).
- Spread and pip value matter: we estimate pip value per unit and size positions to risk a fixed USD per trade.
