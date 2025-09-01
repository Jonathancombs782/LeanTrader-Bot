# Go-Live Runbook

This short runbook explains the required environment variables and safety steps to enable live trading.

Prerequisites
- Ensure you have tested strategies extensively in backtest and paper modes.
- Have monitoring and alerts configured (Prometheus/Grafana, Telegram/Email alerts).

Required environment variables
- ENABLE_LIVE=true           # primary flag to enable live code paths
- # ALLOW_LIVE=true            # additional explicit allow flag (do not set literal in repo)
- LIVE_CONFIRM=YES           # final confirmation required to perform live orders
- API_KEY, API_SECRET        # exchange credentials
- EXCHANGE_ID                # e.g., bybit, binance, paper
- BYBIT_TESTNET=true/false   # if using bybit testnet
- MAX_ORDER_SIZE             # optional max quantity per order
- LIVE_ORDER_USD             # optional USD notional cap per order

Safety checklist (before enabling live)
1. Confirm `EXCHANGE_ID` and `BYBIT_TESTNET` are correct.
2. Confirm API keys are present and scoped to required permissions.
3. Validate `MAX_ORDER_SIZE` and/or `LIVE_ORDER_USD` are set to sensible values.
4. Run smoke tests in paper mode: `python -m run_live --paper` (or run the included tests).
5. Enable live flags only during a maintenance window and monitor behavior.

Rollback
- Immediately unset ENABLE_LIVE or ALLOW_LIVE or set LIVE_CONFIRM to a non-YES value to stop live execution.
- If needed, set EXCHANGE_ID=paper to force dry-run mode.

Notes
- The router enforces multiple safety gates. Live orders require all three: ENABLE_LIVE, ALLOW_LIVE and LIVE_CONFIRM=YES plus API credentials at process start.
- The codebase applies `# noqa: F401` to some imports intentionally retained for dev or optional backends; these do not affect runtime.
