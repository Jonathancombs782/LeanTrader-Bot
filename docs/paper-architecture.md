# Paper-Trading Brain — Architecture

**Status:** Milestone 1 (2026-09-24) — core invariants implemented and tested; updated Nov 11, 2026 (hash-chained ledger, strictly read-only status, replay hardening).
**Branch:** `feature/cdp-signing-helper`

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

- Not a strategy *interface* yet. A trend-v1 strategy exists
  (`paper/strategy.py`: LONG when close>SMA20>SMA50, SHORT when
  reversed) and the evening loop (`paper/daily_loop.py`) scans the
  watchlist and submits its signals through the risk gates — but
  Milestone 2's reproducibility check (replaying a strategy's declared
  inputs to verify its signals) is still open. Signals can also still
  be submitted explicitly (by a human or a script).
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
| `ledger.py` | Append-only JSONL writers (`signals`, `fills`, `risk_events`, `equity`) + `verify_receipts()` that re-hashes receipts + `verify_chain()` that checks the per-line `prev_hash`/`record_sha` hash chain. |
| `engine.py` | `PaperEngine`: submit signal → risk gate → size → simulate fill → update portfolio → ledger everything. |
| `strategy.py` | Trend v1: LONG when close>SMA20>SMA50, SHORT when reversed; stop 1.5× ADR, target 3.0× ADR. |
| `history.py` | Daily bars: CoinGecko `market_chart` (crypto) + Yahoo chart (stocks), with cached payloads and SHA-256 evidence receipts. |
| `daily_loop.py` | Evening loop: one mark snapshot for the watchlist, signal scan, risk gates, one equity row, writes `paper/plans/YYYY-MM-DD.md`. |
| `annotate_ledger.py` | One-time Nov 9, 2026 ledger annotator (phantom fills, broken baselines); refuses once any line carries a `record_sha`. |
| `cli.py` | `python -m paper.cli` — `signal`, `status` (strictly read-only), `roll` (explicit day-roll), `verify` commands. |

## Risk limits (defaults)

| Limit | Default | Behavior on breach |
|---|---|---|
| Starting equity | $100,000 paper | — |
| Max risk per trade | 2% of equity | Trade rejected |
| Max portfolio heat | 6% (sum of open-trade risk) | Trade rejected |
| Max position size | 25% of equity notional | Trade rejected |
| One position per symbol | — | Second fill on an open symbol rejected at submit; in replay a duplicate-position fill is flagged in `replay_diagnostics` and skipped, never overwriting the first position |
| Daily loss halt | −4% day | No new trades rest of day (logged) |
| Kill switch | −15% drawdown from peak | All trading halted, positions flagged (logged) |
| Fee | 10 bps per side | Applied to every fill |
| Slippage | 5 / 15 / 30 bps by tier | Applied to every fill, entries AND exits |

## Accounting rules

- **Sizing uses the simulated fill, not the declared entry.** The engine probes
  the fill price (mid ± tier slippage) first, then sizes quantity and records
  `risk_amount` from the fill-to-stop distance. A stale entry can never
  understate the true stop loss. Stop equal to the fill price is rejected
  (undefined risk).
- **The daily PnL baseline rolls every UTC day.** `trading_day` + a
  `day_roll` risk event persist the marker; ledger replay restores it.
  The roll happens in the evening loop, on signal submission, and via
  the explicit `paper.cli roll` command — never on `status`, which is
  strictly read-only.
- **Every ledger line is hash-chained** (Nov 11, 2026). New lines carry
  `prev_hash` (hash of the previous line) + `record_sha` (SHA-256 of
  the line's content including `prev_hash`); `verify_chain()` fails on
  any edited, deleted, reordered, or unchained-after-chained line.
  Lines written before the chain are a legacy prefix, never rewritten;
  the first chained line anchors on the last legacy line's raw bytes.
- **The feed cache is keyed by requested asset IDs.** A cached response for one
  symbol set is never served to a different request.
- **Evidence snapshots are content-addressed** (`coingecko_<sha256[:16]>.json`),
  so concurrent fetches can never overwrite each other's cited bytes.
- **Every ledger row carries a two-axis classification** (adopted Nov 9,
  2026). Axis 1, fill legitimacy: `legit` or `phantom` — a phantom fill is
  a recorded fill that never represented a real entry, and replay skips it;
  nothing is ever deleted, bogus rows are annotated in place. Axis 2, mark
  state: `ok` or `indeterminate: ...` — an equity row or day_roll baseline
  computed from a missing or stale mark is refused or labeled, never
  silently recorded as truth.
- **The day-roll fails closed.** `roll_day_if_new()` refuses when any open
  position's mark is missing or stale, records one `day_roll_refused`
  event per trading day, and leaves the old baseline in place. A baseline
  reset is a `baseline_correction` risk event, which replay applies like a
  day_roll and which supersedes every day_roll before it.
- **One mark snapshot per run.** The evening loop loads every watchlist
  mark before gating any signal, and records its equity row from the same
  snapshot the plans used — so a plan and its row can never disagree the
  way the Nov 3 plan ($89,422.15, SOL $93.47) and row ($89,413.83,
  SOL $93.43) did. A snapshot that would exclude an open position's value
  is skipped, never recorded.
- **The fill path reads its own writes.** `submit_signal()` refreshes
  positions from the ledger before gating, so a fill logged by another
  process (or by a fresh engine that never replayed) is visible to the
  single-position check. That is the Nov 4, 2026 fix: four SOL fills in
  one second while a long was already open.

## Receipt format

```json
{
  "type": "coingecko_price_snapshot",
  "source": "https://api.coingecko.com/api/v3/simple/price?...",
  "observed_at": "2026-09-24T22:10:00Z",
  "sha256": "9f2c…",
  "payload_path": "paper/evidence/coingecko_<sha256[:16]>.json"
}
```

Anyone with the payload file can recompute the hash. Anyone without it can
re-fetch the same endpoint and compare structure (prices move; structure and
provenance don't).

## Milestone roadmap

- **M1 (this):** Core invariants — signals, receipts, fills, risk gates,
  portfolio accounting, ledger, and ledger replay (so `paper.cli status`
  reflects the recorded history instead of a fresh portfolio). Tested.
- **M2:** Strategy interface — a strategy submits signals with declared inputs;
  engine replays inputs to verify reproducibility.
- **M3:** On-chain receipt collectors (DEX trades, whale wallets) as first-class
  signal inputs.
- **M4:** Public evidence ledger publishing (the "receipts drawer" for the
  JTCombs channel).
- **M5 (separately approved):** Live execution adapter with fresh restricted
  credentials. Never before M1–M4 prove themselves on paper.
