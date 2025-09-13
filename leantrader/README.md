# LeanTrader (Starter Stack)

Ultra-lean FX bot skeleton with:
- DSL strategies
- Feature engineering stubs (RSI/ADX/FVG/structure)
- Backtest engine + metrics
- Risk/execution placeholders
- Research RAG hooks
- GA Alpha Factory hooks
- Trader-assimilation placeholders

See `QUICKSTART.md` for commands, and `data/keywords` for the machine-readable keyword bank.


## Telegram Signals
Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`. The service will push formatted signals when rules fire.

## API
Run with: `uvicorn leantrader.api.app:app --reload --host ${API_HOST:-0.0.0.0} --port ${API_PORT:-8000}`  
Endpoint: `/signal?pair=EURUSD` reads CSVs from `data/ohlc/` and emits the latest signal (also posts to Telegram if env is set).

## CLI
`python -m leantrader.cli --pair EURUSD --loop --sleep 30`


## Agents (Load Splitting)
Use `leantrader.agents.orchestrator.spawn_agents` to start per-pair workers that handle data→signal→Telegram for each asset independently.


## Session Micro-Manager & Learning
- `sessions/manager.py`: determine session (Asia/London/NY) and track per-session stats.
- `learners/bandit.py`: contextual bandit (Thompson-like) to pick policies per session/regime.
- `learners/replay.py`: replay buffer of trades for continuous learning.
- `learners/curriculum.py`: unlock skills as performance thresholds are met.
- `analytics/attribution.py`: basic PnL attribution scaffold.
- `live/micromanager.py`: ties sessions + bandit + replay to guide decisions and steady improvements.


## Global Risk Lock & News Filter
- `risk/global_lock.py`: Redis-based lock to pause all agents after daily max drawdown breach.  
- `risk/news_filter.py`: stub for high-impact event blackout windows (extend with API fetch).  
Configure `REDIS_URL` in `.env` or docker-compose.  


## Interactive Telegram (Premium)
- Premium list: `data/telegram/premium.json` (add your channel/chat IDs).
- Inline buttons: Buy/Sell, Set SL/TP, Open in Broker.
- Chart snapshots auto-attached; caption includes analytics explanation.
- Webhook stub: `POST /telegram/callback` — extend to route orders to your chosen broker platforms.


## Broker UI (FastAPI)
- `GET /trade?pair=EURUSD&side=buy&price=1.23456` renders a confirmation page.
- `POST /trade/confirm` returns a JSON echo now — extend it to route orders through `execution/broker.py`.
- Add authentication before production use.


## User Profiles & Dummy Broker
- **Profiles**: `users/store.py` stores user profiles and **encrypted API keys** (Fernet, key from `USER_SECRET_KEY`).
- **Admin Endpoints**:
  - `POST /admin/user/create?user_id=demo&display_name=Demo`
  - `POST /admin/user/setkeys?user_id=demo` with JSON body `{fx_key, fx_secret, ccxt_key, ccxt_secret}`
  - `GET /admin/user/get?user_id=demo`
- **Dummy Broker**: `execution/broker_emulator.py` simulates latency, slippage, and partial fills for local testing.
  - Use it to test order flow and UI updates before connecting real brokers.


## Broker Mode Switch
`.env` → `BROKER_MODE=emu|fx|ccxt` controls where orders go.
- **emu**: in-process BrokerEmulator (safe testing)
- **fx**: your FX broker connector (to implement)
- **ccxt**: crypto exchanges via CCXT (to implement)

## Premium vs General Signals
- Premium chats (IDs in `data/telegram/premium.json`) get interactive trade buttons.
- General/public chats receive the same **signal + chart + analytics** but **no buttons**.


## Verification
Review **TRADING_SEQUENCES_CHECKLIST.md** before go-live or major refactors to ensure full coverage of trading sequences, confluence, risk, and safety.


## FX Connectors
- **OANDA**: `FX_BACKEND=oanda` with `OANDA_API_TOKEN`, `OANDA_ACCOUNT_ID`, `***REDACTED***|live`.
- **MT5**: `FX_BACKEND=mt5` with `pip install MetaTrader5` and a running terminal.

## Admin UI
- `/admin` → manage premium chat IDs and set user keys.
- Data stored in `data/telegram/premium.json` and `data/store/users.json`.

## Nginx TLS Reverse Proxy
- Compose file: `deploy/docker-compose.nginx.yml`
- Put certs at `deploy/nginx/certs/fullchain.pem` and `deploy/nginx/certs/privkey.pem`.
- Launch: `docker compose -f deploy/docker-compose.nginx.yml up --build`
