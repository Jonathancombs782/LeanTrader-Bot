# LeanTrader-Bot

Paper-trading brain for stocks and crypto. **Paper only — no live trading, no real money.**

## The one entry point

```bash
python -m paper.cli --help
python -m paper.cli signal --symbol BTC --side long --entry 83000 --stop 81000 --target 87000
python -m paper.cli status
python -m paper.cli roll
python -m paper.cli verify
```

- `signal` — evaluate a trade idea against code-enforced risk limits, simulate the fill (fees + slippage), and append it to the ledger.
- `status` — rebuild the portfolio by replaying the append-only ledger and print the current snapshot. Strictly read-only: it records nothing. The day-roll is an explicit `roll` command (also run by the evening loop), never a side effect of reading the status.
- `verify` — re-hash every receipt's stored payload against its recorded SHA-256, verify the ledger hash chain (per-line `prev_hash` + `record_sha`; lines written before Nov 11, 2026 are legacy, unchained, and left as they are), and replay the ledger surfacing orphan/duplicate diagnostics.

## What it is

- `paper/` — the paper-trading brain: signals with hashed evidence snapshots, a $100,000 paper portfolio, simulated fills/fees/slippage/PnL, append-only ledgers, and code-enforced risk limits (2% max risk/trade, 6% portfolio heat, 25% max position, −4% daily-loss halt, −15% drawdown kill switch).
- `docs/paper-architecture.md` — the architecture spec (milestones M1–M5).
- `tests/test_paper_brain.py` — 54 tests covering the brain (168 tests repo-wide across 29 test files).

## What it is not (yet)

Live execution is milestone M5 and is **not implemented** in the paper brain. The repo does include a Binance signing helper (`binance_client.py`, stdlib-only) that signs requests with API keys taken from the environment — public and read-only endpoints by default, live orders off unless `BINANCE_ALLOW_LIVE_ORDERS=1`, and no withdrawal function. No keys are stored in the repo. The roadmap is paper-first: M1 core accounting → M2 strategy interface → M3 on-chain receipts → M4 public evidence ledger → M5 separately-approved live execution.

## Development

```bash
pip install -r requirements-test.txt
ENABLE_LIVE=false pytest -q        # full suite; live execution is always disabled in tests
python .github/scripts/import_smoke.py
```

Supporting modules (`risk/`, `strategies/`, `marketdata/`, exchange adapters, etc.) exist for research and testing. The `nightly_quantum_backtest.yml` workflow runs a synthetic quantum A/B backtest on schedule.

## History

This repo was consolidated in October 2026 around the paper-trading brain. Hundreds of legacy bot variants, deploy scripts, backups, and archives were removed (all preserved in git history). The `runtime/webhook_server.py` module referenced by old Telegram tooling was never committed; its test skips cleanly.
