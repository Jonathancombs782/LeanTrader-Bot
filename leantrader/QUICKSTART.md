# Quickstart

```bash
python -m venv .venv && source .venv/bin/activate     # (Windows: .venv\Scripts\activate)
pip install -e .
cp .env.example .env
pytest
```

## Copilot / GPT-5 Agent Prompts
Paste these one by one to expand modules:

1) **Data feeds (OHLC)**
> Implement `data.feeds.get_ohlc(pair: str, timeframe: str, start: str, end: str)` returning OHLC DataFrame.
> Add resampling helpers to build frames for D1/H4/H1/M15 aligned by index.

2) **Microstructure**
> Upgrade `features/microstructure.py` with proper swing high/low (Fractals/ZigZag), liquidity sweeps, and precise FVG.
> Add equal highs/lows detection and label stop runs.

3) **Execution + costs**
> Create `execution/execution_ai.py` with adaptive VWAP/TWAP/POV using rolling slippage per pair/session.
> Integrate costs into backtest.

4) **Risk (regime-aware)**
> In `risk/guardrails.py` add regime-aware sizing using ADX/realized vol/news proximity.
> Add daily loss cap + cooldown.

5) **Regime + Meta-router**
> Implement `alpha/change_point.py` (Bayesian online change-point).
> In `policy/meta_router.py` infer trend/range/news using ADX, Hurst, calendar signals.

6) **RAG Research**
> Implement `research/rag.py` ingest(pdf/html/url) -> vector store; `research/extract.py` prose->DSL conversion.

7) **GA Alpha Factory**
> In `alpha/ga_search.py` add fitness: walk-forward multi-pair, Sharpe, maxDD, stability, turnover penalty.

8) **Trader Assimilation (IL/IRL)**
> Build `policy/trader_ensemble.py` with imitation learning + inverse RL and a gating network.

9) **Journal & Attribution**
> Implement `live/journal.py` + `backtest/metrics.py` PnL attribution & counterfactuals.

Run tests with `pytest` and extend coverage.
