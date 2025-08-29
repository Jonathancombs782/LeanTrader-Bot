from __future__ import annotations
import os, math, time
import pandas as pd
from dotenv import load_dotenv
from traders_core.connectors.crypto_ccxt import ohlcv_df, ticker_price, market_buy, market_sell, market_info
from traders_core.storage.registry import load_latest_tagged, load_latest
from traders_core.features.pipeline import make_features
from traders_core.utils.ta import atr
from traders_core.observability.metrics import METRICS
from traders_core.research.regime import tag_regimes

load_dotenv()
TRADING_MODE    = os.getenv("TRADING_MODE","paper").lower()
CRYPTO_TESTNET  = (os.getenv("CRYPTO_TESTNET","true").lower() == "true")

def _round_amount(amount: float, prec: int) -> float:
    q = 10 ** prec
    return int(amount * q) / q

def _emulate_oco(symbol_key: str, get_price, sl: float, tp: float, poll: int):
    """Client-side OCO: close paper position when SL or TP hit; for live, send market close."""
    from traders_core.sim.paper_broker import PaperBroker
    brk = PaperBroker()
    while True:
        px = float(get_price())
        # mark-to-market will close on exact SL/TP in paper mode
        brk.mark_to_market(symbol_key, px)
        # If no position left, break
        if not brk.positions(symbol_key):
            break
        time.sleep(max(1, poll))

def decide_and_execute_crypto(exchange: str, symbol: str, timeframe: str, cfg: dict, models_dir: str, lookback_days: int = 120):
    sym_key = symbol.replace("/","_")
    model, meta = load_latest(sym_key, timeframe, models_dir)
    if model is None:
        return {"status":"no_model"}

    df = ohlcv_df(exchange, symbol, timeframe, lookback_days, CRYPTO_TESTNET)
    feats = make_features(df, rsi_window=cfg["risk"]["atr_window"], atr_window=cfg["risk"]["atr_window"])
    X_live = feats[meta["features"]].iloc[[-1]]
    prob = float(getattr(model, "predict_proba")(X_live)[0,1])

    # Regime tag (calm/storm) and probability gate
    reg = tag_regimes(df["close"], cfg["regimes"]["vol_window"], cfg["regimes"]["calm_quantile"])
    regime_now = reg.iloc[-1]
    gate = 0.55 if regime_now == "storm" else 0.5
    side = 1 if prob > gate else 0

    sym_key = symbol.replace("/","_")
tag = "storm" if regime_now == "storm" else "calm"
model, meta = load_latest_tagged(sym_key, timeframe, tag, models_dir)
if model is None:
    model, meta = load_latest(sym_key, timeframe, models_dir)  # fallback

    price = float(df["close"].iloc[-1])
    latest_atr = float(atr(df.tail(200), cfg["risk"]["atr_window"]).iloc[-1])
    if side == 0:
        METRICS.last_signal.labels(venue="crypto", symbol=symbol).set(0)
        METRICS.latest_prob.labels(venue="crypto", symbol=symbol).set(prob)
        return {"status":"flat", "prob":prob, "regime": regime_now}

    mkt = market_info(exchange, symbol, CRYPTO_TESTNET)
    equity = float(cfg["risk"].get("equity_usd", 50.0))
    risk_money = equity * cfg["risk"]["per_trade_risk_pct"]
    raw_amount = risk_money / max(latest_atr, 1e-9)
    min_amount_cost = mkt["min_cost"] / price
    amount = max(raw_amount, min_amount_cost, mkt["min_qty"])
    amount = _round_amount(amount, mkt["amount_prec"])

    sl = price - cfg["risk"]["atr_stop_mult"] * latest_atr
    tp = price + cfg["risk"]["atr_tp_mult"] * latest_atr

    METRICS.latest_prob.labels(venue="crypto", symbol=symbol).set(prob)
    METRICS.last_signal.labels(venue="crypto", symbol=symbol).set(1)

    if TRADING_MODE == "paper":
        from traders_core.sim.paper_broker import PaperBroker
        brk = PaperBroker()
        fill = brk.market_buy(symbol=f"CRYPTO:{symbol}", price=price, qty=amount, fee_rate=mkt["taker"], sl=sl, tp=tp)
        METRICS.orders_total.labels(venue="crypto", symbol=symbol, status="paper").inc()

        if cfg.get("oco",{}).get("enabled", True):
            # spawn a lightweight OCO emulator loop (blocking in our simple loop; okay since we poll every tick)
            _emulate_oco(f"CRYPTO:{symbol}", lambda: ticker_price(exchange, symbol, CRYPTO_TESTNET), sl, tp, cfg["oco"]["poll_sec"])

        return {"status":"paper_filled", "prob":prob, "amount":amount, "price":price, "sl":sl, "tp":tp, "regime":regime_now, "fill":fill}

    # LIVE: send market buy; emulate OCO client-side by watching price and sending market sell on trigger.
    try:
        res = market_buy(exchange, symbol, amount, CRYPTO_TESTNET)
        METRICS.orders_total.labels(venue="crypto", symbol=symbol, status="live_sent").inc()
        if cfg.get("oco",{}).get("enabled", True):
            def _live_close():
                px = float(ticker_price(exchange, symbol, CRYPTO_TESTNET))
                hit_sl = px <= sl
                hit_tp = px >= tp
                if hit_sl or hit_tp:
                    try:
                        market_sell(exchange, symbol, amount, CRYPTO_TESTNET)
                    except Exception:
                        pass
                    return True
                return False
            # quick loop (non-threaded): check once; orchestration calls this function every signal pass
            _live_close()
        return {"status":"live_sent", "id":res.get("id"), "amount":amount, "prob":prob, "price":price, "regime":regime_now}
    except Exception as e:
        METRICS.orders_total.labels(venue="crypto", symbol=symbol, status="live_error").inc()
        return {"status":"live_error", "error":str(e), "regime":regime_now}
