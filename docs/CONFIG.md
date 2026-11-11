# Configuration — single source of truth

Consolidated Nov 11, 2026 (B5). Before that, this repo had two env
templates sharing 7 of 34/53 keys, three config systems, and four
dependency manifests disagreeing in both directions.

## The one template

`.env.template` is the ONLY env template. Copy it to `.env` and fill in
real values; never commit `.env` (`.gitignore` ignores `.env*` except
`.env.template`). The old `.env.example` was merged into `.env.template`
and removed.

Contradictions the merge resolved (template wins):

- `ENABLE_LIVE` was `true` AND `false` in `.env.example` — the template
  has one value: `false`.
- `BYBIT_TESTNET` was `false` in the example, `true` in the template —
  the template's `true` stands.
- The example's stray `***REDACTED***` scrub-marker line is gone.
- The realistic-looking MT5 values in `traders_core/.env.example`
  (`MT5_LOGIN=12345678`) are now unmistakable placeholders
  (`<YOUR_MT5_LOGIN>` etc.).

## The one loader

`settings.py` (`Settings`, loaded from `.env` via `load_dotenv()`) is the
canonical loader. `config.py` is a compatibility re-export of it.
Legacy modules still read `os.getenv` directly in places — new code
should read `settings` / `config` instead; migrating every legacy call
site is future work, not part of this consolidation.

## Key naming

- Binance secret: the template's canonical name is `BINANCE_SECRET_KEY`;
  `BINANCE_API_SECRET` is accepted as an alias (`settings.py`,
  `binance_client.py`). Either works; `BINANCE_API_SECRET` wins if both
  are set. The rest of the repo (`config.py`, `settings.py`) uses the
  `BINANCE_API_SECRET` spelling.
- Live-trading gates: `ENABLE_LIVE=false`, `ALLOW_LIVE=false`,
  `LIVE_CONFIRM=NO` in the template. The paper brain never reads these;
  the legacy routers and the Binance helper gate on them.

## Dependency manifests

Reconciled Nov 11, 2026 (B5) against a mechanical import scan of every
`.py` file in the repo:

- `requirements.txt` — the full-app manifest: exactly the third-party
  packages some module imports (plus `uvicorn`, the ASGI runner for
  `runtime/webhook_server.py`, which is CLI-invoked, not imported).
  Packages nothing imports were dropped (tensorflow, torch, ta-lib,
  yfinance, python-binance, alpaca-trade-api, ib-insync,
  websocket-client, streamlit, plotly, dash, sqlalchemy, schedule,
  loguru, twilio, bcrypt, joblib, scikit-learn, scipy, statsmodels,
  pydantic, tenacity, tiktoken, networkx, numba, python-telegram-bot,
  aiohttp, httpx, web3). The heavy ML stack stays available as
  `pyproject.toml` optional dependencies.
- `pyproject.toml` — same imported set as `requirements.txt`, plus the
  optional ML extras. `pythonpath` is `["."]` (there is no `src/`).
- `requirements-test.txt` — what the test suite and the modules under
  test import. `httpx` stays because `fastapi.testclient` needs it.
  `scikit-learn`, `scipy`, and `web3` were dropped: nothing in tests
  or in the modules under test imports them.
- `traders_core/requirements.core.txt` — what `traders_core/` imports
  (pandas, numpy, python-dotenv, MetaTrader5, PyYAML, ccxt). The
  duplicated `scikit-learn` line and the unimported packages are gone.

Floors are kept where the repo already pinned them or the dev venv
proves them; newly declared packages with no prior pin are unpinned.
