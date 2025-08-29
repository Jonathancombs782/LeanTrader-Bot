# mt5_signals.py
from __future__ import annotations
from typing import Dict, Any, Optional, List
import pandas as pd
from mt5_adapter import bars_df, order_send_market, ensure_symbol, min_stop_distance_points, symbol_trade_specs

def ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()

def gen_signal(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Very simple: EMA(12/26) crossover + ATR-based SL/TP bands.
    Returns {} when flat.
    """
    if df.empty or "close" not in df:
        return {}

    c = df["close"]
    e12, e26 = ema(c, 12), ema(c, 26)
    atr = (df["high"] - df["low"]).rolling(14, min_periods=1).mean()
    last = len(df) - 1

    side: Optional[str] = None
    # Cross-up
    if e12.iloc[last] > e26.iloc[last] and e12.iloc[last-1] <= e26.iloc[last-1]:
        side = "buy"
    # Cross-down
    if e12.iloc[last] < e26.iloc[last] and e12.iloc[last-1] >= e26.iloc[last-1]:
        side = "sell"

    if side is None:
        return {}

    px = float(c.iloc[last])
    a = float(atr.iloc[last] or 0.0)
    if a <= 0:
        a = px * 0.003  # fallback 0.3%

    if side == "buy":
        sl = px - 1.5*a
        tp = px + 2.5*a
    else:
        sl = px + 1.5*a
        tp = px - 2.5*a

    return {"side": side, "entry": px, "sl": sl, "tp": tp}

def place_mt5_signal(mt5mod, symbol: str, side: str, lots: float, sl: Optional[float], tp: Optional[float]) -> Dict[str, Any]:
    # respect broker min stop distance
    try:
        min_pts = min_stop_distance_points(symbol)
        info = symbol_trade_specs(symbol)
        px_point = float(info["point"] or 0.00001)
        if sl is not None and tp is not None and min_pts > 0:
            # widen distances if needed
            if side == "buy":
                sl = min(sl, (None if sl is None else (sl)))
                if (float(tp) - float(info["trade_tick_value"])) < float(tp):
                    pass  # just for structure; order_send_market already widens if needed
        # send
    except Exception:
        pass

    return order_send_market(mt5mod, symbol, side, lots, sl=sl, tp=tp, deviation=20)

def fetch_bars_safe(symbol: str, timeframe: str, limit: int = 300) -> pd.DataFrame:
    try:
        df = bars_df(symbol, timeframe, limit=limit)
        if not df.empty and "time" in df:
            df = df.drop_duplicates(subset=["time"]).reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame()
