# mt5_adapter.py
from __future__ import annotations

import os
from typing import Optional, Dict, Any, List

from dotenv import load_dotenv

try:
    import MetaTrader5 as mt5  # type: ignore
except Exception:  # pragma: no cover
    mt5 = None

load_dotenv()


# ------------------ .env helpers ------------------

def _envs() -> Dict[str, str]:
    return {
        "PATH":     (os.getenv("MT5_PATH") or "").strip(),
        "LOGIN":    (os.getenv("MT5_LOGIN") or "").strip(),
        "PASSWORD": (os.getenv("MT5_PASSWORD") or "").strip(),
        "SERVER":   (os.getenv("MT5_SERVER") or "").strip(),
    }


# ------------------ init ------------------

def mt5_init(path: Optional[str] = None):
    """
    Initialize/attach to MetaTrader 5.
    Uses MT5_PATH / MT5_LOGIN / MT5_PASSWORD / MT5_SERVER from .env
    """
    if mt5 is None:
        raise RuntimeError("MetaTrader5 python package is not installed")

    env = _envs()
    use_path = path or (env["PATH"] or None)

    # Attach/launch terminal
    ok = mt5.initialize(path=use_path)
    if not ok:
        code, desc = mt5.last_error()
        raise RuntimeError(f"mt5.initialize failed: ({code}) {desc}")

    # Optional login (if you keep a logged-in terminal, this can be omitted)
    if env["LOGIN"] and env["PASSWORD"] and env["SERVER"]:
        if not mt5.login(int(env["LOGIN"]), password=env["PASSWORD"], server=env["SERVER"]):
            code, desc = mt5.last_error()
            mt5.shutdown()
            raise RuntimeError(f"mt5.login failed: ({code}) {desc} (server={env['SERVER']})")

    return mt5


# ------------------ symbol helpers ------------------

def ensure_symbol(symbol: str) -> None:
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"Unknown symbol {symbol!r}")
    if not info.visible:
        if not mt5.symbol_select(symbol, True):
            raise RuntimeError(f"symbol_select({symbol}) failed")


def symbol_trade_specs(symbol: str) -> Dict[str, Any]:
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"symbol_info({symbol}) is None")
    return {
        "digits": int(info.digits),
        "point": float(info.point),
        "volume_min": float(info.volume_min),
        "volume_step": float(info.volume_step),
        "volume_max": float(info.volume_max),
        "trade_stops_level": int(info.trade_stops_level),
        "freeze_level": int(getattr(info, "freeze_level", 0)),
        "trade_contract_size": float(getattr(info, "trade_contract_size", 0)),
        "trade_tick_value": float(getattr(info, "trade_tick_value", 0)),
    }


def normalize_volume(symbol: str, lots: float) -> float:
    s = symbol_trade_specs(symbol)
    step = s["volume_step"] or 0.01
    v = round(max(s["volume_min"], min(lots, s["volume_max"])) / step) * step
    return max(s["volume_min"], min(v, s["volume_max"]))


def min_stop_distance_points(symbol: str) -> int:
    s = symbol_trade_specs(symbol)
    # brokers may enforce either stops_level or freeze_level – respect the max
    return max(int(s["trade_stops_level"]), int(s["freeze_level"]))


# ------------------ data: robust bars_df ------------------

def bars_df(symbol: str, timeframe_str: str, limit: int = 200):
    """
    Return a DataFrame of bars with stable columns:
    time, open, high, low, close, tick_volume, spread, real_volume
    Fixes the 'KeyError: time' by constructing from dtype names when needed.
    """
    import pandas as pd
    import numpy as np

    ensure_symbol(symbol)

    tf_map = {
        "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1, "MN1": mt5.TIMEFRAME_MN1,
    }
    tf = tf_map.get(timeframe_str.upper())
    if tf is None:
        raise ValueError(f"Unsupported timeframe '{timeframe_str}'")

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, int(limit))
    if rates is None:
        code, desc = mt5.last_error()
        raise RuntimeError(f"copy_rates_from_pos failed: ({code}) {desc}")

    # rates is usually a numpy structured array
    if hasattr(rates, "dtype") and getattr(rates.dtype, "names", None):
        cols = list(rates.dtype.names or [])
        df = pd.DataFrame(rates.tolist(), columns=cols)
    else:
        # fallback: build from list of dicts or tuples
        try:
            df = pd.DataFrame(list(rates))
        except Exception:
            df = pd.DataFrame()

    if df.empty:
        return df

    # ensure required columns exist
    if "time" not in df.columns:
        # sometimes the field name is b'time' or 0..n; try to coerce
        for c in df.columns:
            if str(c).lower() == "time":
                df.rename(columns={c: "time"}, inplace=True)
                break
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], unit="s", errors="coerce")

    expected = ["open", "high", "low", "close"]
    for c in expected:
        if c not in df.columns:
            # try byte column names like b'open'
            for k in df.columns:
                if str(k).lower() == c:
                    df.rename(columns={k: c}, inplace=True)
                    break

    # keep a stable view
    keep = [c for c in ["time", "open", "high", "low", "close",
                        "tick_volume", "spread", "real_volume"] if c in df.columns]
    return df[keep].copy()


# ------------------ account summary ------------------

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
        f"Margin: {float(info.margin):.2f}    Positions: {pos_n}  (uPnL {profit:.2f})",
    ]


# ------------------ order helper ------------------

def order_send_market(symbol: str, side: str, lots: float,
                      sl: Optional[float] = None, tp: Optional[float] = None,
                      deviation: int = 20) -> Dict[str, Any]:
    """
    Market order with optional SL/TP.
    Use keyword args when calling to avoid argument collision.
    """
    ensure_symbol(symbol)
    side = side.lower().strip()
    lots_n = normalize_volume(symbol, lots)

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return {"ok": False, "retcode": -1, "comment": "no tick", "deal": 0}

    price = tick.ask if side == "buy" else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "type": order_type,
        "volume": lots_n,
        "price": price,
        "sl": float(sl or 0.0),
        "tp": float(tp or 0.0),
        "deviation": int(deviation),
        "type_filling": mt5.ORDER_FILLING_FOK,
        "type_time": mt5.ORDER_TIME_GTC,
        "comment": "LeanTrader single-shot",
    }
    res = mt5.order_send(req)

    # retry with IOC if FOK rejected
    if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
        req["type_filling"] = mt5.ORDER_FILLING_IOC
        res = mt5.order_send(req)

    return {
        "ok": bool(res and res.retcode == mt5.TRADE_RETCODE_DONE),
        "retcode": getattr(res, "retcode", -1),
        "comment": getattr(res, "comment", ""),
        "deal": getattr(res, "deal", 0),
        "order": getattr(res, "order", 0),
        "request": req,
    }
