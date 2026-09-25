# Paper-Trading Brain — Architecture

**Status:** Milestone 1 (2026-09-24) — core invariants implemented and tested.
**Branch:** `feature/paper-trading-brain`

## The idea nobody has built

Every trading bot posts signals. Nobody posts signals where **each signal carries
independently verifiable receipts** — the raw market data and on-chain facts the
signal was built from, hashed and timestamped, so anyone can re-check the claim
without trusting us.

This package is the foundation of that system:

1. **Signals are evidence-bearing.** A signal is not just "buy SOL" — it is a
   signed bundle: thesis + entry/stop/target + the exact data snapshot it was
   derived from (price feed payload, hashed) + any on-chain receipts (tx hashes,
   explorer URLs). Reproduce the inputs, reproduce the signal.
2. **Paper portfolio, real accounting.** $100k of play money with real fill
   simulation (slippage + fees), mark-to-market equity, realized/unrealized PnL,
   and an append-only ledger. No exchange account, no API keys, no real dollars.
3. **Hard risk limits, enforced in code.** Not guidelines — gates. A trade that
   breaches a limit is rejected and the rejection is logged. Daily loss halt and
   a drawdown kill switch stop the bleeding automatically.
4. **Public evidence ledger.** Every signal, fill, and risk event lands in
   append-only JSONL. When this goes live in public, the ledger is the receipts
   drawer the YouTube channel points at.

## What this is NOT (yet)

- Not a strategy. Milestone 1 has no alpha engine — signals are submitted
  explicitly (by a human, a script, or a future strategy module). The brain
  validates, sizes, simulates, and records. Strategy comes in milestone 2.
- Not live trading. Nothing here touches an exchange. Real-money execution is a
  separately approved future phase with fresh, restricted credentials.
- Not financial advice. Educational / research software.

## Package layout (`paper/`)

| Module | Responsibility |
|---|---|
| `universe.py` | Tradable asset universe. `BLUE_CHIPS` (19 assets) is the default seed; swap in any list. |
| `receipts.py` | Evidence receipt model + SHA-256 snapshot hashing. A receipt pins a claim to data anyone can re-fetch. |
| `feeds.py` | Public price data (CoinGecko free API, no key). Responses cached on disk; every snapshot saved to the evidence dir with its hash. Stdlib only. |
| `signals.py` | Signal dataclass + validation (side/entry/stop/target consistency), `inputs_hash` for reproducibility. |
| `fills.py` | Fill simulator: mid-price ± slippage by liquidity tier, fee in bps. Returns effective fill price + cost breakdown. |
| `risk.py` | `RiskLimits` + gate checks: per-trade risk, portfolio heat, max position size, daily loss halt, drawdown kill switch. Breaches raise `RiskBreach` and are ledger-logged. |
| `portfolio.py` | `PaperPortfolio`: cash, positions, mark-to-market equity, realized/unrealized PnL, daily PnL. |
| `ledger.py` | Append-only JSONL writers (`signals`, `fills`, `risk_events`, `equity`) + `verify()` that re-hashes receipts. |
| `engine.py` | `PaperEngine`: submit signal → risk gate → size → simulate fill → update portfolio → ledger everything. |
| `cli.py` | `python -m paper.cli` — `signal`, `status`, `verify` commands. |

## Risk limits (defaults)

| Limit | Default | Behavior on breach |
|---|---|---|
| Starting equity | $100,000 paper | — |
| Max risk per trade | 2% of equity | Trade rejected |
| Max portfolio heat | 6% (sum of open-trade risk) | Trade rejected |
| Max position size | 25% of equity notional | Trade rejected |
| Daily loss halt | −4% day | No new trades rest of day (logged) |
| Kill switch | −15% drawdown from peak | All trading halted, positions flagged (logged) |
| Fee | 10 bps per side | Applied to every fill |
| Slippage | 5 / 15 / 30 bps by tier | Applied to every fill |

## Receipt format

```json
{
  "type": "coingecko_price_snapshot",
  "source": "https://api.coingecko.com/api/v3/simple/price?...",
  "observed_at": "2026-09-24T22:10:00Z",
  "sha256": "9f2c…",
  "payload_path": "paper/evidence/coingecko_20260924T221000Z.json"
}
```

Anyone with the payload file can recompute the hash. Anyone without it can
re-fetch the same endpoint and compare structure (prices move; structure and
provenance don't).

## Milestone roadmap

- **M1 (this):** Core invariants — signals, receipts, fills, risk gates,
  portfolio accounting, ledger. Tested.
- **M2:** Strategy interface — a strategy submits signals with declared inputs;
  engine replays inputs to verify reproducibility.
- **M3:** On-chain receipt collectors (DEX trades, whale wallets) as first-class
  signal inputs.
- **M4:** Public evidence ledger publishing (the "receipts drawer" for the
  JTCombs channel).
- **M5 (separately approved):** Live execution adapter with fresh restricted
  credentials. Never before M1–M4 prove themselves on paper.
