# Live deployment checklist (paper -> testnet -> live)

Follow these steps before enabling live trading. Do them in order and run paper/testnet for a minimum of 2-4 weeks of data collection.

1) Paper-mode validation
   - Set `EXCHANGE_ID=paper` and `ENABLE_LIVE=false` or use `tools/run_bot_paper.py`.
   - Run for 2-4 weeks, collect PnL and trade logs, and confirm strategies' edge is positive.

2) Testnet/sandbox
   - Switch to real exchange id (e.g. `EXCHANGE_ID=bybit`) and `BYBIT_TESTNET=true`.
   - Keep `ENABLE_LIVE=false` to avoid placing real orders. Confirm connectivity and order flows against testnet.

3) Live gating (required)
  - Set `ENABLE_LIVE=true` and `ALLOW_LIVE=<your_value>` to indicate intent.
   - Also set `LIVE_CONFIRM=YES` (this repository requires this additional confirmation to allow live orders).
   - Provide API keys via environment variables, not committed files:
     - `API_KEY` / `API_SECRET` or `BYBIT_API_KEY` / `BYBIT_API_SECRET`.

4) Risk limits (strongly recommended)
   - `MAX_ORDER_SIZE` (base asset units) — hard cap per order.
   - `LIVE_ORDER_USD` (USD): per-order notional cap enforced at runtime.
   - Start with small sizes and low leverage.

5) Monitoring & rollback
   - Enable Telegram/email notifier and alerting for PnL drawdown thresholds.
   - Keep an operator on-call and a manual kill-switch (`ALLOW_LIVE=false`) for emergencies.

6) Continuous testing
   - Add CI smoke tests that run in `paper` mode to catch accidental live-sending code.

If you want, I can now:
- Run linters and fix low-risk issues
- Add more tests for CCXT/Bybit and MT5 adapters
- Implement telemetry & alerting examplesThis repo supports safe paper, testnet and live runs.

Quick commands:
- Paper (safe dry-run)
  - python tools/run_bot_paper.py

  - Testnet (demo)
  - Set testnet flag and testnet keys, then:
    - PowerShell example (use placeholders instead of literal true/1 values):
      $env:ENABLE_LIVE="<true|false>"; $env:ALLOW_LIVE="<your_value>"; $env:API_KEY="<test_key>"; $env:API_SECRET="<test_secret>"; $env:BYBIT_TESTNET="<true|false>"
    - python tools/run_bot_live.py

-- Live (real funds) — *be extremely careful*
- Set real keys and safety limits (use placeholders where applicable):
  - ENABLE_LIVE=<your_value> (e.g. "true" when you intend to go live)
  - ALLOW_LIVE=<your_value>
  - API_KEY / API_SECRET
  - MAX_ORDER_SIZE (recommended very small)
  - LIVE_ORDER_USD or LIVE_ORDER_AMOUNT
  - python tools/run_bot_live.py

Notes:
- Both ENABLE_LIVE and ALLOW_LIVE must be set to put the bot into live mode.
- MAX_ORDER_SIZE prevents oversized orders.
- Run `python tools/run_scans.py` and `python -m tests.smoke_test` before enabling live to verify the codebase.
