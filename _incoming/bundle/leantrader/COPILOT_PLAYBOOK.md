# Copilot Playbook: Wire LeanTrader into Your Repo

Paste these prompts in order after unzipping:

### 1) Data Feeds
Implement `src/leantrader/data/feeds.py` with:
- `get_ohlc(pair: str, timeframe: str, start: str, end: str) -> DataFrame[time, open, high, low, close]` using my broker/ccxt.
- A resampler to build D1/H4/H1/M15 frames aligned by the M15 index.
- Write CSVs to `data/ohlc/<PAIR>_<TF>.csv` so API/CLI can read them.

### 2) Microstructure Upgrade
Improve `features/microstructure.py`:
- Real swing high/low (Fractals/ZigZag), equal highs/lows, stop-run detection.
- Precise FVG from wicks/bodies.
- Replace RSI-div placeholder with proper divergence.

### 3) Execution & Costs
Create `execution/execution_ai.py`:
- Adaptive VWAP/TWAP/POV chooser using rolling slippage per pair/session.
- Integrate into `backtest/engine.py` to charge realistic costs and partial fills.

### 4) Risk (Regime-aware)
In `risk/guardrails.py`:
- Map ADX, realized volatility, and news proximity to risk fraction in `[PER_TRADE_RISK_MIN, PER_TRADE_RISK_MAX]`.
- Enforce `MAX_DAILY_DD` cutoff + cooldown.

### 5) Regime + Router
Add `alpha/change_point.py` for Bayesian change-point detection.
In `policy/meta_router.py`:
- Compute regime = trend/range/news via ADX, Hurst exponent, and news calendar.
- Route to `house_smc` on trend; `trader_ensemble` on range; reduce risk pre-news.

### 6) Trader Assimilation
Create `policy/trader_ensemble.py`:
- Behavior Cloning (state→action) + Inverse RL (reward recovery).
- Distill multiple trader styles; gating network picks per context.

### 7) Research RAG
Implement `research/rag.py` + `research/extract.py`:
- ingest(pdf/html/url) → vector store (FAISS or equivalent).
- extract DSL rules from prose; validate with backtests; save to `dsl/`.

### 8) GA Alpha Factory
Enhance `alpha/ga_search.py` fitness:
- Walk-forward across pairs/sessions; score by Sharpe, maxDD, stability, turnover penalty.

### 9) Journal & Attribution
Add `live/journal.py` and extend `backtest/metrics.py`:
- Log all decisions and outcomes; decompose PnL into entry/exit/SL/TP/costs.

### 10) Telegram Accuracy Guard
- Add a validator that only posts when `go==1` AND confluence >= threshold (e.g., ADX>20 AND trend-aligned).
- Include context: timeframes that confirmed, ATR-based SL/TP, risk fraction.

Final step: create a small script to backfill last N bars and produce a sample Telegram post for QA.
