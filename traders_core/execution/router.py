from __future__ import annotations
import os, math
from dotenv import load_dotenv
from traders_core.storage.registry import load_latest
from traders_core.mt5_adapter import market_buy, symbol_info, copy_rates_days
from traders_core.features.pipeline import rates_to_df, make_features
from traders_core.utils.ta import atr
from traders_core.observability.metrics import METRICS

load_dotenv()
TRADING_MODE = os.getenv("TRADING_MODE","paper").lower()  # paper | live

def _round_lot(volume: float, min_lot: float, lot_step: float, max_lot: float) -> float:
    steps = round(volume / lot_step)
    v = steps * lot_step
    v = max(min_lot, min(max_lot, v))
    return round(v, 2)

def value_per_price_unit(si) -> float:
    if si.trade_tick_size <= 0: return 0.0
    return si.trade_tick_value / si.trade_tick_size

def decide_and_execute_mt5(symbol: str, timeframe: str, cfg: dict, models_dir: str, research_lookback_days: int = 10):
    model, meta = load_latest(symbol, timeframe, models_dir)
    if model is None: return {"status":"no_model"}

    rates = copy_rates_days(symbol, timeframe, research_lookback_days)
    df = rates_to_df(rates)
    feats = make_features(df, rsi_window=cfg["risk"]["atr_window"], atr_window=cfg["risk"]["atr_window"])
    X_live = feats[meta["features"]].iloc[[-1]]

    prob = float(model.predict_proba(X_live)[0,1])
    side = 1 if prob > 0.5 else 0  # 1=long, 0=flat
    METRICS.latest_prob.labels(venue="mt5", symbol=symbol).set(prob)
    METRICS.last_signal.labels(venue="mt5", symbol=symbol).set(side)

    if side == 0:
        return {"status":"flat", "prob":prob}

    si = symbol_info(symbol)
    latest_atr = atr(df.tail(100), cfg["risk"]["atr_window"]).iloc[-1]
    v_per_unit = value_per_price_unit(si)  # per 1 lot
    equity = getattr(si, "equity", None) or 5000.0
    risk_money = equity * cfg["risk"]["per_trade_risk_pct"]
    vol = cfg["risk"]["min_lot"] if (v_per_unit <= 0 or latest_atr <= 0) else risk_money / (float(latest_atr) * v_per_unit)
    vol = _round_lot(vol, cfg["risk"]["min_lot"], cfg["risk"]["lot_step"], cfg["risk"]["max_lot"])

    px = df["close"].iloc[-1]
    sl = float(px - cfg["risk"]["atr_stop_mult"] * latest_atr)
    tp = float(px + cfg["risk"]["atr_tp_mult"] * latest_atr)

    if TRADING_MODE == "paper":
        from traders_core.sim.paper_broker import PaperBroker
        brk = PaperBroker()
        fill = brk.market_buy(symbol=f"MT5:{symbol}", price=float(px), qty=float(vol), fee_rate=0.0, sl=sl, tp=tp)
        METRICS.orders_total.labels(venue="mt5", symbol=symbol, status="paper").inc()
        return {"status":"paper_filled", "prob":prob, "volume":float(vol), "price":float(px), "sl":sl, "tp":tp, "fill":fill}

    res = market_buy(symbol, float(vol), sl, tp)
    ok = (res is not None) and (getattr(res, "retcode", None) in (10009, 10008, 0))
    METRICS.orders_total.labels(venue="mt5", symbol=symbol, status=("live_sent" if ok else "live_error")).inc()
    return {"status": "live_sent" if ok else "live_error", "retcode": getattr(res, "retcode", None), "prob": prob,
            "volume": float(vol), "sl": sl, "tp": tp}
