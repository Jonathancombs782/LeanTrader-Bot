# Copilot Addendum: FX + Crypto + Agents

**A) CCXT/Exchange wiring**
Implement exchange selection and symbol normalization in `execution/broker.py` and `utils/symbols.py`:
- Map `EURUSD`→`EUR/USD` (fx) and `BTCUSDT`→`BTC/USDT` (crypto).
- Add precision, lot size, and tick-size rounding helpers.

**B) Perps & Funding (crypto)**
Add in `execution/broker.py` methods for perpetual swaps (leverage, isolated/cross). Track funding rates and apply them in the backtester.

**C) Agent scaling**
In `agents/orchestrator.py`, add a supervisor that restarts crashed workers, and a queue to pass control messages (pause, resume, risk throttle). Optionally switch to Ray actors.
