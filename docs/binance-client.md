# Binance signing helper — setup

File: `binance_client.py` (repo root). Stdlib only, no installs.

## Why this file exists

Muse cannot sign Binance requests — the secret never leaves the vault, so no
code on Muse's side can compute the HMAC-SHA256 signature Binance requires
for account/trading calls. This helper runs on Jonathan's own machine, where
the secret lives in his environment. Muse's Binance API connection attempt
was declined by the platform for exactly this reason (Nov 10, 2026).

## Setup (on your machine)

1. **Make the key** — Binance.US (or Binance.com) → account menu →
   API Management → Create API → **System-generated** (HMAC key + secret).
   - Name it something clear, e.g. `LeanTrader-Bot`.
   - Permissions: **Enable Read** only, to start. Turn on **Enable Spot
     Trading** only when you explicitly decide to place live orders.
   - **Leave Enable Withdrawals OFF. Always.**
   - If your machine has a stable IP, restrict the key to that IP.
   - Copy the secret **now** — Binance never shows it again.
2. **Put the keys in the environment** (or a local `.env` file next to the
   script — never commit a filled-in `.env`):
   ```sh
   export BINANCE_API_KEY=<your key>
   export BINANCE_API_SECRET=<your secret>
   # Binance.US is the default. For Binance.com:
   export BINANCE_BASE_URL=https://api.binance.com
   # Spot testnet (no real money — best first run):
   export BINANCE_BASE_URL=https://testnet.binance.vision
   ```
3. **Test with no real money first** — point at the testnet, then run:
   ```sh
   python3 binance_client.py selftest
   ```
   Public checks (ping, server time, BTCUSDT price) need no key. With keys
   set it also does a signed read-only account check and lists non-zero
   balances. It never prints a key or secret.
4. **Switch to the real exchange** only after the testnet selftest passes:
   unset `BINANCE_BASE_URL` (defaults to Binance.US) or set it to the
   matching real host, then run `selftest` again.

## Commands

```sh
python3 binance_client.py ping                 # connectivity
python3 binance_client.py time                 # Binance server time
python3 binance_client.py price BTCUSDT        # ticker price
python3 binance_client.py klines BTCUSDT --interval 1h --limit 5
python3 binance_client.py depth BTCUSDT
python3 binance_client.py account              # signed, read-only balances
python3 binance_client.py orders BTCUSDT       # signed, open orders
python3 binance_client.py allorders BTCUSDT    # signed, order history
```

## Live orders — paper-first

`place_order` is **off** unless `BINANCE_ALLOW_LIVE_ORDERS=1` is set in the
environment. Leave it off while the bot is paper-first. There is no
withdrawal function in the file, on purpose.

```sh
BINANCE_ALLOW_LIVE_ORDERS=1 python3 binance_client.py order BTCUSDT BUY 0.001 --price 70000
```

## Errors you may see

- `-1021` — clock skew: sync the machine's clock.
- `-1022` — bad signature: wrong secret, or the key was made on the other
  Binance (`.com` key against `.us` host, or vice versa).
- `-2015` — invalid API key, or the key's IP restriction blocks this machine.
- `-2010` — the key lacks the permission for that call (e.g. trading not
  enabled for an order). Note: unlike `-1021`/`-1022`/`-2015`, `-2010`
  has no friendly-hint branch in `binance_client.py` — the CLI prints
  Binance's raw message for it.

## Notes

- Keys are read from `BINANCE_API_KEY` + `BINANCE_API_SECRET` (the repo's
  `config.py` names) — `BINANCE_SECRET_KEY` (the `.env.template` name) is
  also accepted.
- `recvWindow` is 5000 ms. Timestamps come from the local clock.
- Rate limits are per-IP; the helper makes one call per command, far inside
  them.
