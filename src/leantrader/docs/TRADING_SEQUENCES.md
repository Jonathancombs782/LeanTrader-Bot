# LeanTrader — Comprehensive Trading Sequences & Coverage Matrix

This matrix enumerates every major step a pro bot should implement end-to-end.
Each item shows **module hooks** you already have and **gaps** to fill.

## A. Market Data Ingestion
- Sources: FX broker API/WebSocket, CCXT (crypto), CSV backfill, RAG research features
- Resampling & alignment: D1/H4/H1/M15 aligned to M15 index (`data/feeds.py`)
- Dedup/validation, clock skew, missing bars handling

## B. Feature Engineering (multi-timeframe & session-aware)
- Core TA: EMA/HMA/SMA, RSI, ADX, ATR, Bollinger, MACD
- Microstructure: HH/HL/LH/LL, equal highs/lows, liquidity sweep, FVG (wick/body), divergence
- Regime: ADX/Hurst, change-points, volatility state, news proximity
- Session tags (Asia/London/NY), day-of-week/time-of-day effects

## C. Signal Generation
- Strategy DSL (gold XAUUSD playbook + house SMC)
- Confluence gating (trend align + ADX + FVG/RSI-div + optional liquidity sweep)
- Router (dispatcher/meta-router) choosing best policy per **session × regime**
- News/Risk guard: blackout & global lock

## D. Sizing & Risk
- Per-trade risk fraction by regime/session
- SL/TP from ATR & structure (swing highs/lows)
- Exposure netting & correlation caps
- Max daily drawdown lock + cooldown (Redis)
- Portfolio limits: symbol, sector (USD exposure), leverage

## E. Execution
- `BROKER_MODE=emu|fx|ccxt` unified path
- Slippage model, partial fills, retries & idempotency
- Maker/limit vs market routing; VWAP/TWAP/POV (execution_ai.py)
- Funding (perps), fees, spread controls, order life-cycle states

## F. Post-Trade & Learning
- Journal & attribution (entry edge, exit edge, costs)
- Replay buffer; bandit selection (policy per session/regime)
- Curriculum unlocks (range, news scalp, orderflow/FVG)
- Walk-forward validation; parameter sweeps; promotion to prod

## G. Distribution & UX
- Telegram premium & general channels (buttons only for premium)
- Charts per signal with analytics explanations
- Broker UI + Orders/Balance dashboard (WebSocket live updates)

## H. Reliability & Security
- Health checks, retries, circuit breakers
- Secrets: encrypted keys, token auth for admin & UI
- Audit logs for signal → order → fill chain

## I. Tests & Monitoring
- Unit & integration tests per module
- Backtest parity tests (signals vs live)
- Metrics: win rate, Sharpe, maxDD, turnover, slippage, latency
- Alerting on anomalies (low hit-rate, high slippage, stale data)

Use `COPILOT_PLAYBOOK_FINAL.md` plus *Sessions*, *Addendum* and this matrix to reach full coverage.
