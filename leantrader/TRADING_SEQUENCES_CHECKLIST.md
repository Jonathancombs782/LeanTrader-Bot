# LeanTrader — Pro Trading Sequences & Coverage

This checklist captures *what the bot needs to know/do* to analyse and trade systematically. Use it to verify completeness when wiring features and strategies.

## 1) Market Structure & Microstructure
- Trend ID: EMA/HMA/KAMA crosses; slope filters
- Fractals/ZigZag swing HH/HL vs LH/LL; breaks of structure (BOS/CHOCH)
- Fair Value Gaps (body+wick), order blocks (mitigation), liquidity sweeps (equal highs/lows, stop runs)
- Divergences: RSI/MACD/OBV vs price
- Volatility regime: ATR, Parkinson, realized/parked vol, volatility contraction/expansion

## 2) Multi-Timeframe Confluence
- Alignment rules: D1/H4 trend, H1 context, M15 entry
- Session filters: Asia/London/NY open/close; overlap boosts
- News proximity: blackout window for high-impact events

## 3) Signals Catalogue (core + alt styles)
- Trend-Follow: pullback entries, breakout + retest, channel break
- Mean-Reversion: range edge fade, bollinger/MFI extremes, RSI-2 / RSI-14 reversion
- SMC/ICT: FVG + OB + BOS/CHOCH, liquidity purge → revert, premium/discount zones
- Wyckoff: accumulation/distribution phases (PS, SC, AR, ST, Spring/Upthrust), sign-of-strength/weakness
- Elliott (optional): motive/corrective detection heuristics
- Pattern bank: flags, triangles, wedges, H&S, double tops/bottoms (time-weighted/quality scoring)

## 4) Risk, Sizing, & Execution
- Risk fraction per trade with regime/session multipliers
- Global caps: max daily DD, max open risk, exposure netting by currency/sector
- Costs: spread, slippage, commissions, funding (perps)
- Execution styles: Market/VWAP/TWAP/POV chooser by liquidity and slippage

## 5) Data Integrity
- Clean OHLC, dedup, timezone normalization, resampler alignment (M15 base)
- Corporate actions (for equities) *N/A for FX/crypto*, but handle symbol migrations

## 6) Evaluation & Learning
- Backtests: in-sample vs out-of-sample; walk-forward validation
- Bandit policy selection by session/regime; replay buffer for thresholds
- Curriculum unlock for advanced tactics when stable

## 7) Telemetry, Journaling, & Explainability
- Journal entries for each decision with features snapshot and outcomes
- Telegram analytics summary per signal; chart snapshots
- Attributions: entry edge vs exit management vs costs

## 8) Live Controls & Safety
- Global risk lock (Redis), news pre-filter
- Premium gating for interactive trade buttons
- Broker health checks & fallback routes

> Tip: Keep this list in PRs so you never ship a change that regresses core trading sequences.
