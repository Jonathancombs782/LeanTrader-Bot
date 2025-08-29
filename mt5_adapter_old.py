# mt5_adapter.py
from __future__ import annotations

import os
from typing import Optional, Dict, Any, List

from dotenv import load_dotenv

# MetaTrader5 binding (graceful message if missing)
try:
    import MetaTrader5 as mt5  # type: ignore
except Exception as _e:  # pragma: no cover
    mt5 = None

load_dotenv()


# ----------------------------- env helpers -----------------------------

def _envs() -> Dict[str, str]:
    """Read MT5 settings from environment (.env)."""
    return {
        "PATH":   (os.getenv("MT5_PATH") or "").strip(),
        "LOGIN":  (os.getenv("MT5_LOGIN") or "").strip(),
        "PASSWORD": (os.getenv("MT5_PASSWORD") or "").strip(),
        "SERVER": (os.getenv("MT5_SERVER") or "").strip(),
    }


# ------------------------------ init ----------------------------------

def mt5_init(path: Optional[str] = None):
    """
    Initialize/attach to MetaTrader 5 terminal.
    - Uses MT5_PATH/LOGIN/PASSWORD/SERVER from .env unless arguments are provided.
    - If terminal is already running, initialize() attaches to it.
    Raises RuntimeError on failure with mt5.last_error() details.
    """
    if mt5 is None:
        raise RuntimeError("MetaTrader5 package is not installed (pip install MetaTrader5)")

    env = _envs()
    use_path = path or (env["PATH"] if env["PATH"] else None)

    # initialize (with or without explicit path)
    ok = mt5.initialize(path=use_path)
    if not ok:
        code, desc = mt5.last_error()
        raise RuntimeError(f"mt5.initialize failed: ({code}) {desc}")

    # optional login if creds provided
    if env["LOGIN"] and env["PASSWORD"] and env["SERVER"]:
        if not mt5.login(int(env["LOGIN"]), password=env["PASSWORD"], server=env["SERVER"]):
            code, desc = mt5.last_error()
            mt5.shutdown()
            raise RuntimeError(f"mt5.login failed: ({code}) {desc} (server={env['SERVER']})")

    return mt5


# --------------------------- symbol utilities --------------------------

def ensure_symbol(symbol: str) -> None:
    """Ensure symbol exists and is visible."""
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"Unknown symbol {symbol!r}")
    if not info.visible:
        if not mt5.symbol_select(symbol, True):
            raise RuntimeError(f"symbol_select({symbol}) failed")


def symbol_trade_specs(symbol: str) -> Dict[str, Any]:
    """Return broker trade constraints for a symbol."""
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"symbol_info({symbol}) is None")
    return {
        "digits": int(info.digits),
        "point": float(info.point),
        "volume_min": float(info.volume_min),
        "volume_step": float(info.volume_step),
        "volume_max": float(info.volume_max),
        "trade_stops_level": int(getattr(info, "trade_stops_level", 0)),
        "freeze_level": int(getattr(info, "freeze_level", 0)),
        "trade_contract_size": float(getattr(info, "trade_contract_size", 0)),
        "trade_tick_value": float(getattr(info, "trade_tick_value", 0)),
    }


def normalize_volume(symbol: str, lots: float) -> float:
    """Clamp & round lots to broker step/min/max."""
    s = symbol_trade_specs(symbol)
    step = s["volume_step"] or 0.01
    v = round(max(s["volume_min"], min(lots, s["volume_max"])) / step) * step
    return max(s["volume_min"], min(v, s["volume_max"]))


def min_stop_distance_points(symbol: str) -> int:
    """Minimum stop distance in *points* enforced by the broker."""
    s = symbol_trade_specs(symbol)
    return max(int(s["trade_stops_level"]), int(s["freeze_level"]))


# ------------------------------ market data ----------------------------

def bars_df(symbol: str, timeframe_str: str, limit: int = 200):
    """
    Return a DataFrame with stable OHLCV columns:
    ['time','open','high','low','close','tick_volume','spread','real_volume'].
    Handles installs where pandas creates numeric column names (0..N-1).
    """
    import pandas as pd

    ensure_symbol(symbol)

    tf_map = {
        "M1":  mt5.TIMEFRAME_M1,   "M5":  mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,  "M30": mt5.TIMEFRAME_M30,
        "H1":  mt5.TIMEFRAME_H1,   "H4":  mt5.TIMEFRAME_H4,
        "D1":  mt5.TIMEFRAME_D1,   "W1":  mt5.TIMEFRAME_W1,
        "MN1": mt5.TIMEFRAME_MN1,
    }
    tf = tf_map.get(timeframe_str.upper())
    if tf is None:
        raise ValueError(f"Unsupported timeframe '{timeframe_str}'")

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, int(limit))
    if rates is None:
        code, desc = mt5.last_error()
        raise RuntimeError(f"copy_rates_from_pos failed: ({code}) {desc}")

    # Structured array -> DataFrame. Fallback to list if needed.
    try:
        df = pd.DataFrame(rates)
    except Exception:
        df = pd.DataFrame(list(rates))

    if df.empty:
        return df

    # Some environments end up with numeric columns (0..7). Rename explicitly.
    if "time" not in df.columns:
        expected_cols = ["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]
        if len(df.columns) >= len(expected_cols):
            df = df.iloc[:, :len(expected_cols)]
            df.columns = expected_cols

    # Convert time -> datetime if present
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], unit="s", errors="coerce")

    return df


# --------------------------- account snapshot --------------------------

def account_summary_lines() -> List[str]:
    info = mt5.account_info()
    if info is None:
        code, desc = mt5.last_error()
        return [f"account_info failed: ({code}) {desc}"]
    pos = mt5.positions_get()
    pos_n = 0 if pos is None else len(pos)
    profit = 0.0
    if pos:
        try:
            profit = float(sum(float(p.profit or 0) for p in pos))
        except Exception:
            pass
    return [
        f"Account: {getattr(info, 'name', '')} ({getattr(info, 'login', '')})",
        f"Balance: {float(info.balance):.2f}  Equity: {float(info.equity):.2f}",
        f"Margin:  {float(info.margin):.2f}  Positions: {pos_n}  (uPnL {profit:.2f})",
    ]


# ------------------------------- orders --------------------------------

def order_send_market(
    symbol: str,
    side: str,
    lots: float,
    sl: Optional[float] = None,
    tp: Optional[float] = None,
    deviation: int = 20,
) -> Dict[str, Any]:
    """
    Place a market order with optional SL/TP.
    - Auto-normalizes volume to broker lot step/min/max.
    - Retries with IOC if FOK rejected.
    Returns dict {ok, retcode, comment, deal, order, request}
    """
    ensure_symbol(symbol)
    side = side.lower().strip()
    lots_n = normalize_volume(symbol, lots)

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return {"ok": False, "retcode": -1, "comment": "no tick", "deal": 0, "order": 0, "request": {}}

    price = float(tick.ask if side == "buy" else tick.bid)
    order_type = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "type": order_type,
        "volume": float(lots_n),
        "price": price,
        "sl": float(sl or 0.0),
        "tp": float(tp or 0.0),
        "deviation": int(deviation),
        "type_filling": mt5.ORDER_FILLING_FOK,
        "type_time": mt5.ORDER_TIME_GTC,
        "comment": "lt-single",
    }

    res = mt5.order_send(req)

    # If not done, try again with IOC (more permissive on fills)
    if (res is None) or (getattr(res, "retcode", 0) != mt5.TRADE_RETCODE_DONE):
        req["type_filling"] = mt5.ORDER_FILLING_IOC
        res = mt5.order_send(req)

    return {
        "ok": bool(res and getattr(res, "retcode", 0) == mt5.TRADE_RETCODE_DONE),
        "retcode": getattr(res, "retcode", -1),
        "comment": getattr(res, "comment", ""),
        "deal": getattr(res, "deal", 0),
        "order": getattr(res, "order", 0),
        "request": req,
    }
