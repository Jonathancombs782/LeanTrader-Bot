"""FX fetcher via MetaTrader5 for learning dataset generation.

Environment:
  ENABLE_FX_LEARNING_MT5=true
  MT5_LOGIN / MT5_PASSWORD / MT5_SERVER must be set (and platform installed).

Outputs CSV to runtime/data/fx_<SYMBOL>_<TF>.csv with columns time,open,high,low,close,volume
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import List

try:
    import MetaTrader5 as mt5
except Exception:  # pragma: no cover
    mt5 = None  # type: ignore


_TF_MAP = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}


def _mt5_tf(tf: str):
    tf = tf.upper().strip()
    return {
        "M1": getattr(mt5, "TIMEFRAME_M1", None),
        "M5": getattr(mt5, "TIMEFRAME_M5", None),
        "M15": getattr(mt5, "TIMEFRAME_M15", None),
        "M30": getattr(mt5, "TIMEFRAME_M30", None),
        "H1": getattr(mt5, "TIMEFRAME_H1", None),
        "H4": getattr(mt5, "TIMEFRAME_H4", None),
        "D1": getattr(mt5, "TIMEFRAME_D1", None),
    }.get(tf)


def init_mt5() -> bool:
    """Initialize MetaTrader5 connection.

    Tries MT5_PATH/MTS_PATH when provided. If login envs are set, attempts login; otherwise
    relies on the currently running terminal session. Returns True on successful initialize.
    """
    if mt5 is None:
        return False
    path = os.getenv("MT5_PATH") or os.getenv("MTS_PATH")
    login = os.getenv("MT5_LOGIN")
    password = os.getenv("MT5_PASSWORD")
    server = os.getenv("MT5_SERVER")
    try:
        ok = mt5.initialize(path=path) if path else mt5.initialize()
        if not ok:
            return False
        # Optional login when credentials provided
        if login and password and server:
            if not mt5.login(int(login), password=str(password), server=str(server)):
                # keep the session if terminal is already logged in; only treat as fatal when no session exists
                # users frequently run MT5 terminal manually and rely on attached session
                info = mt5.account_info()
                if info is None:
                    return False
        return True
    except Exception:
        try:
            mt5.shutdown()
        except Exception:
            pass
        return False


def fetch_fx(symbol: str, tf: str, limit: int = 200) -> List[List[float]]:
    if mt5 is None:
        return []
    timeframe = _mt5_tf(tf)
    if timeframe is None:
        return []
    try:
        # ensure symbol selected
        try:
            info = mt5.symbol_info(symbol)
            if info and not info.visible:
                mt5.symbol_select(symbol, True)
        except Exception:
            pass
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, limit)
        if rates is None:
            return []
        out: List[List[float]] = []
        for r in rates:
            ts = int(r["time"]) * 1000
            out.append([ts, float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), float(r["tick_volume"])])
        return out
    except Exception:
        return []


def save_csv(symbol: str, tf: str, rows: List[List[float]]) -> str:
    p = Path("runtime") / "data"
    p.mkdir(parents=True, exist_ok=True)
    path = p / f"fx_{symbol}_{tf}.csv"
    try:
        import csv

        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["time", "open", "high", "low", "close", "volume"])
            for r in rows:
                w.writerow(r)
    except Exception:
        pass
    return str(path)


if __name__ == "__main__":
    import sys

    sym = sys.argv[1] if len(sys.argv) > 1 else "EURUSD"
    tf = sys.argv[2] if len(sys.argv) > 2 else "M15"
    lim = int(sys.argv[3]) if len(sys.argv) > 3 else 200
    if not init_mt5():
        print("mt5 init failed")
        sys.exit(2)
    rows = fetch_fx(sym, tf, lim)
    if not rows:
        print("no rows")
        sys.exit(1)
    out = save_csv(sym, tf, rows)
    print("wrote", out)
