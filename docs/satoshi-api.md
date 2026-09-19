# Coinbase "satoshi API" — setup & safety

`marketdata/satoshi_api.py` + `cli/satoshi.py` give LeanTrader-Bot a
Coinbase Advanced Trade market-data feed with satoshi-denominated pricing.

## What works without any key (default, read-only)

```bash
python cli/satoshi.py price                 # BTC-USD spot + sats stats
python cli/satoshi.py stats --product BTC-USD
python cli/satoshi.py candles --granularity ONE_HOUR --days 1
```

These hit only public endpoints (`GET /api/v3/brokerage/market/...`). No
account, no signature, no money movement — ever.

Strategies can consume the same data in-process:

```python
from marketdata.satoshi_api import btc_sats_snapshot
snap = btc_sats_snapshot()   # price_usd, usd_per_sat, sats_per_usd, ...
```

## Authenticated (read-only) access — CDP API key

Needed for account balances (`list_accounts`). Still read-only.

1. Create a key at <https://portal.cdp.coinbase.com> (EC P-256 key).
2. Download the JSON and keep it **outside the repo**, e.g.
   `~/.config/leantrader/cdp_api_key.json`.
3. Point the bot at it — pick one:

```bash
export COINBASE_CDP_KEY_PATH="$HOME/.config/leantrader/cdp_api_key.json"
# ...or, without a file:
export COINBASE_CDP_KEY_NAME="<key name>"
export COINBASE_CDP_PRIVATE_KEY="<PEM text>"
```

```bash
python cli/satoshi.py accounts
```

The module never prints or logs key material. JWTs are minted per-request
(ES256, `uri: "<METHOD> <host><path>"` claim) and expire in 120 seconds.

## Live trading — deliberately hard to enable

`create_market_order` / `cancel_order` exist for completeness but are **inert**
unless you explicitly opt in:

```bash
export LEANTRADER_LIVE_TRADING=1
```

Without that exact value, every trading call raises
`LiveTradingDisabledError` instead of touching the exchange. The CLI does not
expose order placement at all.

## Key hygiene

* The key file must never be committed. `.gitignore` covers
  `*cdp_api_key*.json`, `*coinbase_cdp*.json`, and `*.pem`.
* If a key ever lands in chat/logs/git, rotate it in the CDP portal and treat
  the old one as compromised.
* Tests use throwaway generated keys and mocked HTTP only
  (`tests/test_satoshi_api.py`) — no network, no real credentials.

## Endpoints used

| Call | Method / path | Auth |
|---|---|---|
| `product()` | `GET /api/v3/brokerage/market/products/{id}` | none |
| `ticker()` | `GET /api/v3/brokerage/market/products/{id}/ticker` | none |
| `best_bid_ask()` | `GET /api/v3/brokerage/market/best_bid_ask` | none |
| `candles()` | `GET /api/v3/brokerage/market/products/{id}/candles` | none |
| `list_products()` | `GET /api/v3/brokerage/market/products` | none |
| `list_accounts()` | `GET /api/v3/brokerage/accounts` | ES256 JWT |
| `create_market_order()` | `POST /api/v3/brokerage/orders` | JWT + `LEANTRADER_LIVE_TRADING=1` |
| `cancel_order()` | `POST /api/v3/brokerage/orders/batch_cancel` | JWT + `LEANTRADER_LIVE_TRADING=1` |

Docs: <https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/>
