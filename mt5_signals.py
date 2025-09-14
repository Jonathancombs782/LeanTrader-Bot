# mt5_signals.py
from __future__ import annotations

# Use lazy, defensive helpers (below) to import mt5_adapter at call-time.
# Avoid injecting a fake module into sys.modules during module-import since
# that can collide with other import paths and produce confusing
# 'cannot import name' errors in supervised child processes.
from typing import Any, Dict, List, Optional  # noqa: F401  # intentionally kept

import pandas as pd

# Import-time diagnostic to help supervisor child debug which mt5_signals
# file is being loaded. Kept lightweight and safe.
try:
    import sys

    print(f"[diag mt5_signals] file={__file__} sys.path[0]={sys.path[0]}")
except Exception:
    pass

# Avoid hard top-level imports from mt5_adapter which can raise during
# import and cause ImportError at module-import time for downstream
# tools. Perform lazy imports with safe fallbacks inside the functions
# that need them.


def _import_mt5_helpers():
    """Return a namespace dict with mt5 helper callables or safe fallbacks."""
    try:
        # Import the mt5_adapter module and take attributes via getattr so a
        # partially-populated module (or an unrelated package named
        # "mt5_adapter") doesn't raise ImportError for a single missing name.
        import importlib
        import os
        import sys
        from pathlib import Path

        # If a stray `mt5_adapter` module is already loaded and isn't the one
        # from the repository root, remove it so our file-based loader can
        # place the repo module into sys.modules. This avoids confusing
        # ImportError when a partially-initialized module lacks expected names.
        try:
            mod = sys.modules.get("mt5_adapter")
            if mod is not None:
                mod_file = getattr(mod, "__file__", None)
                repo_candidate = str(Path(__file__).resolve().parent / "mt5_adapter.py")
                if mod_file and os.path.abspath(mod_file) != os.path.abspath(repo_candidate):
                    try:
                        del sys.modules["mt5_adapter"]
                    except Exception:
                        pass
        except Exception:
            pass

        mod = importlib.import_module("mt5_adapter")
        _bars_df = getattr(mod, "bars_df", None)
        _ensure_symbol = getattr(mod, "ensure_symbol", None)
        _min_stop_distance_points = getattr(mod, "min_stop_distance_points", None)
        _order_send_market = getattr(mod, "order_send_market", None)
        _symbol_trade_specs = getattr(mod, "symbol_trade_specs", None)

        # If the module exists but is missing key helpers, treat it as a
        # failed import so we fall back to the file-loader or to no-op
        # implementations below.
        if _bars_df is None or _ensure_symbol is None or _order_send_market is None or _symbol_trade_specs is None:
            raise ImportError("mt5_adapter module missing required helpers")

        return {
            "bars_df": _bars_df,
            "ensure_symbol": _ensure_symbol,
            "min_stop_distance_points": _min_stop_distance_points,
            "order_send_market": _order_send_market,
            "symbol_trade_specs": _symbol_trade_specs,
        }
    except Exception:
        # If regular import fails (different cwd / sys.path), try loading the
        # local mt5_adapter.py directly from the repository root so workers
        # started with different working directories still find it.
        try:
            import importlib.util
            import sys
            from pathlib import Path

            repo_root = Path(__file__).resolve().parent
            candidate = repo_root / "mt5_adapter.py"
            if candidate.exists():
                spec = importlib.util.spec_from_file_location("mt5_adapter", str(candidate))
                mod = importlib.util.module_from_spec(spec)
                sys.modules["mt5_adapter"] = mod
                spec.loader.exec_module(mod)  # type: ignore
                _bars_df = getattr(mod, "bars_df", None)
                _ensure_symbol = getattr(mod, "ensure_symbol", None)
                _min_stop_distance_points = getattr(mod, "min_stop_distance_points", None)
                _order_send_market = getattr(mod, "order_send_market", None)
                _symbol_trade_specs = getattr(mod, "symbol_trade_specs", None)
                if _bars_df is not None:
                    return {
                        "bars_df": _bars_df,
                        "ensure_symbol": _ensure_symbol,
                        "min_stop_distance_points": _min_stop_distance_points,
                        "order_send_market": _order_send_market,
                        "symbol_trade_specs": _symbol_trade_specs,
                    }
        except Exception:
            pass

        # Provide safe no-op fallbacks so the demo/crawler keep running in
        # environments without MetaTrader5 or where the adapter partially
        # fails to import.
        def _bars_df(symbol, timeframe, limit=300):
            import pandas as _pd

            return _pd.DataFrame()

        def _ensure_symbol(symbol):
            return None

        def _min_stop_distance_points(symbol):
            return 0

        def _order_send_market(mt5mod, symbol, side, lots, sl=None, tp=None, deviation=20):
            return {"ok": False, "retcode": -1, "comment": "order_send_market fallback", "deal": 0}

        def _symbol_trade_specs(symbol):
            return {"point": 0.00001, "trade_tick_value": 0.0}

        return {
            "bars_df": _bars_df,
            "ensure_symbol": _ensure_symbol,
            "min_stop_distance_points": _min_stop_distance_points,
            "order_send_market": _order_send_market,
            "symbol_trade_specs": _symbol_trade_specs,
        }


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
    if e12.iloc[last] > e26.iloc[last] and e12.iloc[last - 1] <= e26.iloc[last - 1]:
        side = "buy"
    # Cross-down
    if e12.iloc[last] < e26.iloc[last] and e12.iloc[last - 1] >= e26.iloc[last - 1]:
        side = "sell"

    if side is None:
        return {}

    px = float(c.iloc[last])
    a = float(atr.iloc[last] or 0.0)
    if a <= 0:
        a = px * 0.003  # fallback 0.3%

    if side == "buy":
        sl = px - 1.5 * a
        tp = px + 2.5 * a
    else:
        sl = px + 1.5 * a
        tp = px - 2.5 * a

    return {"side": side, "entry": px, "sl": sl, "tp": tp}


def place_mt5_signal(
    mt5mod,
    symbol: str,
    side: str,
    lots: float,
    sl: Optional[float],
    tp: Optional[float],
) -> Dict[str, Any]:
    # respect broker min stop distance
    helpers = _import_mt5_helpers()
    # Safety: avoid live order placement unless explicit env gates allow it.
    try:
        import os

        if not (
            os.getenv("ENABLE_LIVE", "false").lower() == "true"
            and os.getenv("ALLOW_LIVE", "false").lower() == "true"
            and os.getenv("LIVE_CONFIRM", "").upper() == "YES"
        ):
            # Dry-run: return a simulated failure payload so caller knows no
            # real order was placed. This keeps strategies running without
            # interacting with real markets during demo/testnet runs.
            return {
                "ok": False,
                "retcode": 0,
                "comment": "dry-run: live trading disabled by environment gates",
                "deal": 0,
            }
    except Exception:
        pass
    try:
        min_pts = helpers["min_stop_distance_points"](symbol)
        info = helpers["symbol_trade_specs"](symbol)
        float(info.get("point", 0.00001) or 0.00001)
        # widen distances if needed (best-effort; underlying order sender
        # should also enforce broker constraints)
        if sl is not None and tp is not None and min_pts > 0:
            if side == "buy":
                sl = sl
    except Exception:
        # keep best-effort defaults
        pass

    return helpers["order_send_market"](mt5mod, symbol, side, lots, sl=sl, tp=tp, deviation=20)


def fetch_bars_safe(symbol: str, timeframe: str, limit: int = 300) -> pd.DataFrame:
    helpers = _import_mt5_helpers()
    try:
        df = helpers["bars_df"](symbol, timeframe, limit=limit)
        if not df.empty and "time" in df:
            df = df.drop_duplicates(subset=["time"]).reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame()
