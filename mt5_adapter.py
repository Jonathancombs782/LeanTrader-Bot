# mt5_adapter.py
from __future__ import annotations

import os
from typing import Any, Dict, Optional  # noqa: F401  # intentionally kept

from dotenv import load_dotenv

try:
    import MetaTrader5 as mt5  # type: ignore
except Exception:
    mt5 = None

load_dotenv()

# local runtime imports are performed inside functions to avoid top-level side effects


def _envs() -> Dict[str, str]:
    return {
        "PATH": os.getenv("MT5_PATH", ""),
        "LOGIN": os.getenv("MT5_LOGIN", ""),
        "PASSWORD": os.getenv("MT5_PASSWORD", ""),
        "SERVER": os.getenv("MT5_SERVER", ""),
    }


def mt5_init(path: Optional[str] = None):
    if mt5 is None:
        raise RuntimeError("MetaTrader5 package is not installed")
    env = _envs()
    use_path = path or env["PATH"] or None
    if not mt5.initialize(path=use_path):
        code, desc = mt5.last_error()
        raise RuntimeError(f"mt5.initialize failed: ({code}) {desc}")
    if env["LOGIN"] and env["PASSWORD"] and env["SERVER"]:
        if not mt5.login(
            int(env["LOGIN"]), password=env["PASSWORD"], server=env["SERVER"]
        ):
            code, desc = mt5.last_error()
            mt5.shutdown()
            raise RuntimeError(
                f"mt5.login failed: ({code}) {desc} (server={env['SERVER']})"
            )
    return mt5


def ensure_symbol(symbol: str) -> None:
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"Unknown symbol {symbol!r}")
    if not info.visible:
        if not mt5.symbol_select(symbol, True):
            raise RuntimeError(f"symbol_select({symbol}) failed")


def min_stop_distance_points(symbol: str) -> int:
    """Return minimum stop distance in points for a symbol (trade_stops_level or freeze_level).

    Some callers (mt5_signals) expect this helper to exist.
    """
    info = mt5.symbol_info(symbol)
    if info is None:
        return 0
    # some brokers expose 'freeze_level'
    try:
        stops = int(getattr(info, "trade_stops_level", 0) or 0)
    except Exception:
        stops = 0
    try:
        freeze = int(getattr(info, "freeze_level", 0) or 0)
    except Exception:
        freeze = 0
    return max(stops, freeze)


def _normalize_rates_df(df):
    import pandas as pd  # noqa: E402

    if df is None or len(df) == 0:
        return pd.DataFrame(
            columns=[
                "time",
                "open",
                "high",
                "low",
                "close",
                "tick_volume",
                "spread",
                "real_volume",
            ]
        )
    df = pd.DataFrame(df)
    # Normalize common aliases
    lower = {str(c).lower(): c for c in df.columns}
    if "vol" in lower:
        df.rename(columns={lower["vol"]: "tick_volume"}, inplace=True)
    if "volume" in lower and "tick_volume" not in df.columns:
        df.rename(columns={lower["volume"]: "tick_volume"}, inplace=True)
    # Ensure required cols
    required = [
        "time",
        "open",
        "high",
        "low",
        "close",
        "tick_volume",
        "spread",
        "real_volume",
    ]
    for c in required:
        if c not in df.columns:
            df[c] = 0
    try:
        df["time"] = __import__("pandas").to_datetime(df["time"], unit="s", utc=True)
    except Exception:
        pass
    return df[required]


def bars_df(symbol: str, timeframe_str: str, limit: int = 200):
    import pandas as pd  # noqa: E402

    ensure_symbol(symbol)
    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
        "W1": mt5.TIMEFRAME_W1,
        "MN1": mt5.TIMEFRAME_MN1,
    }
    tf = tf_map.get(timeframe_str.upper())
    if tf is None:
        raise ValueError(f"Unsupported timeframe {timeframe_str}")
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, limit)
    if rates is None:
        code, desc = mt5.last_error()
        raise RuntimeError(f"copy_rates_from_pos failed: ({code}) {desc}")
    return _normalize_rates_df(pd.DataFrame(list(rates)))


def account_summary_lines():
    info = mt5.account_info()
    if info is None:
        code, desc = mt5.last_error()
        return [f"account_info failed: ({code}) {desc}"]
    pos = mt5.positions_get()
    pos_n = 0 if pos is None else len(pos)
    u_pnl = 0.0
    if pos:
        try:
            u_pnl = float(sum(float(p.profit or 0) for p in pos))
        except Exception:
            pass
    return [
        f"Account: {getattr(info, 'name', '')} ({getattr(info, 'login', '')})",
        f"Balance: {float(info.balance):.2f}  Equity: {float(info.equity):.2f}",
        f"Margin: {float(info.margin):.2f}    Positions: {pos_n}  (uPnL {u_pnl:.2f})",
    ]


# --- Compatibility wrappers -------------------------------------------------
def symbol_trade_specs(symbol: str) -> Dict[str, Any]:
    """Compatibility shim: delegate to the traders_core adapter implementation.

    Some modules import symbol_trade_specs from the top-level mt5_adapter; modern
    implementation lives under traders_core.mt5_adapter. Keep a thin shim here
    so both import styles work.
    """
    try:
        from traders_core import mt5_adapter as core_mt5  # local import

        return core_mt5.symbol_trade_specs(symbol)
    except Exception:
        # fallback: try to read symbol info directly
        info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"symbol_info({symbol}) is None")
        return {
            "digits": int(getattr(info, "digits", 0)),
            "point": float(getattr(info, "point", 0.0)),
            "volume_min": float(getattr(info, "volume_min", 0.0)),
            "volume_step": float(getattr(info, "volume_step", 0.0)),
            "volume_max": float(getattr(info, "volume_max", 0.0)),
            "trade_stops_level": int(getattr(info, "trade_stops_level", 0)),
            "freeze_level": int(getattr(info, "freeze_level", 0)),
            "trade_contract_size": float(getattr(info, "trade_contract_size", 0.0)),
            "trade_tick_value": float(getattr(info, "trade_tick_value", 0.0)),
        }


def order_send_market(mt5mod, symbol: str, side: str, lots: float, sl: Optional[float] = None, tp: Optional[float] = None, deviation: int = 20) -> Dict[str, Any]:
    """Compatibility shim: accept (mt5mod, ...) signature and delegate to
    traders_core.mt5_adapter.order_send_market which uses global mt5 instance.
    """
    try:
        from traders_core import mt5_adapter as core_mt5  # local import

        # core order_send_market signature: (symbol, side, lots, sl=None, tp=None, deviation=20)
        return core_mt5.order_send_market(symbol, side, lots, sl=sl, tp=tp, deviation=deviation)
    except Exception:
        # If delegation fails, provide a safe failure payload
        return {"ok": False, "retcode": -1, "comment": "order_send_market shim failed", "deal": 0}
