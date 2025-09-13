# Test Checklist

- Data feed integrity (gaps, duplicates, timezone)
- Feature correctness (RSI/ADX/ATR, FVG, structure swings)
- Strategy compile (DSL → runner) and deterministic signals on sample data
- Confluence gating logic (unit tests for thresholds)
- News blackout & risk lock respected in signal path
- Execution routing by BROKER_MODE; emulator partial fills covered
- Orders/Balance UI updates on submit; WebSocket broadcast
- Backtest metrics sanity (Sharpe, maxDD)
- Session bandit learning improves policy selection over time
