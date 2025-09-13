# strategy.py
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

BEST_PATH = os.path.join("reports", "best_params.json")


# ---------- utilities ----------
def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=int(n), adjust=False).mean()


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev = close.shift(1)
    tr = pd.concat([(high - low), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(int(n)).mean()


def _roll_max(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(int(n)).max()


def _roll_min(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(int(n)).min()


# ---------- Strategy 1: Trend + BB squeeze ----------
@dataclass
class TrendBreakoutParams:
    ema_fast: int = 50
    ema_slow: int = 200
    bb_period: int = 20
    bb_std: float = 2.0
    bb_bw_lookback: int = 120
    bb_bw_quantile: float = 0.5
    atr_period: int = 14


class TrendBreakoutStrategy:
    def __init__(
        self,
        ema_fast=50,
        ema_slow=200,
        bb_period=20,
        bb_std=2.0,
        bb_bw_lookback=120,
        bb_bw_quantile=0.5,
        atr_period=14,
    ):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.bb_bw_lookback = bb_bw_lookback
        self.bb_bw_quantile = bb_bw_quantile
        self.atr_period = atr_period

    def entries_and_exits(self, df: pd.DataFrame, atr_stop_mult: float, atr_trail_mult: float):
        d = df.copy()
        d["ema_fast"] = _ema(d["close"], self.ema_fast)
        d["ema_slow"] = _ema(d["close"], self.ema_slow)
        ma = d["close"].rolling(self.bb_period).mean()
        sd = d["close"].rolling(self.bb_period).std(ddof=0)
        upper = ma + self.bb_std * sd
        lower = ma - self.bb_std * sd
        d["bb_bw"] = (upper - lower) / ma.replace(0, np.nan)
        d["bb_thresh"] = d["bb_bw"].rolling(self.bb_bw_lookback).quantile(self.bb_bw_quantile, interpolation="nearest")
        d["squeeze"] = d["bb_bw"] <= d["bb_thresh"]
        d["atr"] = _atr(d, self.atr_period)
        trend_up = d["ema_fast"] > d["ema_slow"]
        breakout = (d["close"] > upper.shift(1)) & d["squeeze"].fillna(False)
        d["long_signal"] = trend_up & breakout
        info = {"atr_stop_mult": atr_stop_mult, "atr_trail_mult": atr_trail_mult}
        return d, info


# ---------- Strategy 2: Naked-Forex price-action ----------
@dataclass
class NakedParams:
    sr_lookback: int = 60  # lookback for swing S/R
    pin_len_mult: float = 1.5  # how long wick vs body
    engulf_body_mult: float = 1.1  # engulf body strength
    atr_period: int = 14


class NakedForexStrategy:
    """
    Pure price action:
      - Swing Support/Resistance from rolling pivots
      - Pin bars (long tail rejection)
      - Bullish/Bearish engulfing (body > previous body)
      - EMA trend filter optional (weak)
    Entry long if:
      - price rejects support (pin bar with long lower wick) OR bullish engulf near support
    """

    def __init__(self, sr_lookback=60, pin_len_mult=1.5, engulf_body_mult=1.1, atr_period=14):
        self.sr_lookback = sr_lookback
        self.pin_len_mult = pin_len_mult
        self.engulf_body_mult = engulf_body_mult
        self.atr_period = atr_period

    @staticmethod
    def _body_len(df):
        return (df["close"] - df["open"]).abs()

    @staticmethod
    def _wick_top(df):
        return df["high"] - df[["open", "close"]].max(axis=1)

    @staticmethod
    def _wick_bot(df):
        return df[["open", "close"]].min(axis=1) - df["low"]

    def entries_and_exits(self, df: pd.DataFrame, atr_stop_mult: float, atr_trail_mult: float):
        d = df.copy()
        d["atr"] = _atr(d, self.atr_period)
        d["body"] = self._body_len(d)
        d["wt"], d["wb"] = self._wick_top(d), self._wick_bot(d)

        # Swing S/R (very light): recent highs/lows
        d["sr_high"] = _roll_max(d["high"], self.sr_lookback).shift(1)
        d["sr_low"] = _roll_min(d["low"], self.sr_lookback).shift(1)

        # Pin bar long: long lower wick, small body, close>open (or close near high)
        pin_long = (d["wb"] > self.pin_len_mult * d["body"]) & (d["close"] > d["open"])
        near_sr = d["low"] <= d["sr_low"] * 1.002  # touched/near support

        # Bullish engulfing near support
        prev_body = d["body"].shift(1)
        engulf = (
            (d["close"] > d["open"])
            & (prev_body > 0)
            & ((d["close"] - d["open"]) > self.engulf_body_mult * prev_body)
            & (d["open"] <= d["close"].shift(1))
        )

        d["long_signal"] = (pin_long | engulf) & near_sr.fillna(False)
        info = {"atr_stop_mult": atr_stop_mult, "atr_trail_mult": atr_trail_mult}
        return d, info


# ---------- registry / resolver ----------
def get_strategy(name: str, **kwargs):
    name = (name or "").lower()
    if name in ("naked", "nakedforex", "priceaction", "pa"):
        return NakedForexStrategy(**kwargs)
    # default
    return TrendBreakoutStrategy(**kwargs)


def resolve_strategy_and_params():
    """
    If reports/best_params.json exists, load it and instantiate the named strategy
    with the stored params. Otherwise return default TrendBreakoutStrategy.
    """
    if os.path.exists(BEST_PATH):
        try:
            with open(BEST_PATH, "r") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("best_params.json must contain a JSON object")
            strat_name = data.get("strategy", "trend")
            params = data.get("params", {})
            strat = get_strategy(strat_name, **params)
            return strat, params
        except Exception as _e:
            print(f"[strategy] failed to load best params: {_e}")

    # default
    default = TrendBreakoutStrategy()
    return default, {
        "ema_fast": default.ema_fast,
        "ema_slow": default.ema_slow,
        "bb_period": default.bb_period,
        "bb_std": default.bb_std,
        "bb_bw_lookback": default.bb_bw_lookback,
        "bb_bw_quantile": default.bb_bw_quantile,
        "atr_period": default.atr_period,
    }


def validate_strategies() -> dict:
    """
    Quick sanity checks for available strategy classes and their parameter dataclasses.
    Returns a dict with per-strategy warnings / basic diagnostics.
    """
    import inspect

    warnings = {}
    try:
        strategies = {
            "TrendBreakoutStrategy": TrendBreakoutStrategy,
            "NakedForexStrategy": NakedForexStrategy,
        }
        params = {
            "TrendBreakoutStrategy": TrendBreakoutParams,
            "NakedForexStrategy": NakedParams,
        }
        for name, cls in strategies.items():
            w = []
            if not inspect.isclass(cls):
                w.append("not a class")
            # entries_and_exits presence and basic signature check
            if not hasattr(cls, "entries_and_exits"):
                w.append("missing entries_and_exits method")
            else:
                if not callable(getattr(cls, "entries_and_exits", None)):
                    w.append("entries_and_exits is not callable")
                try:
                    fn = getattr(cls, "entries_and_exits")
                    sig = inspect.signature(fn)
                    param_names = [p.name for p in sig.parameters.values()]
                    # Expect at least (self, df, ...) or a 'df'/'dataframe' parameter
                    if not any(p in param_names for p in ("df", "dataframe", "ohlcv", "bars")) and len(param_names) < 2:
                        w.append(f"entries_and_exits signature unexpected: {param_names}")
                except Exception as _e:
                    w.append(f"failed to inspect entries_and_exits signature: {_e}")
            # runtime smoke: try calling entries_and_exits with a tiny valid OHLC dataframe
            try:
                inst = cls()  # defaults
                # minimal dataframe (5 rows) with required columns
                sample = pd.DataFrame(
                    {
                        "open": [100.0, 100.2, 100.1, 100.3, 100.0],
                        "high": [100.5, 100.4, 100.6, 100.7, 100.2],
                        "low": [99.8, 100.0, 99.9, 100.1, 99.7],
                        "close": [100.2, 100.1, 100.5, 100.3, 100.1],
                    }
                )
                try:
                    out_df, info = inst.entries_and_exits(sample, atr_stop_mult=1.0, atr_trail_mult=0.5)
                    if not isinstance(out_df, pd.DataFrame):
                        w.append("entries_and_exits did not return a DataFrame as first element")
                    if not isinstance(info, dict):
                        w.append("entries_and_exits did not return an info dict as second element")
                except Exception as _e:
                    w.append(f"entries_and_exits raised at runtime on sample data: {_e}")
            except Exception as _e:
                # instantiation/validation failure
                w.append(f"failed to instantiate or run entries_and_exits: {_e}")
            # simple param checks if dataclass provided
            pcls = params.get(name)
            if pcls:
                try:
                    inst = pcls()  # use defaults
                    for fld, val in vars(inst).items():
                        if isinstance(val, (int, float)):
                            if isinstance(val, int) and val <= 0:
                                w.append(f"param {fld} has non-positive default {val}")
                            if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                                w.append(f"param {fld} default invalid: {val}")
                except Exception as _e:
                    w.append(f"failed to instantiate params: {_e}")
            warnings[name] = w
    except Exception as _e:
        return {"error": str(_e)}
    return warnings


def scan_project_with_model(root: str = ".") -> dict:
    """
    Combined lightweight scan that:
      - runs router.scan_codebase(root)
      - validates strategies in this module
      - optionally collects other-files summary via router.scan_all_files
    """
    try:
        from router import scan_all_files, scan_codebase
    except Exception:
        try:
            from .router import scan_all_files, scan_codebase
        except Exception:
            scan_codebase = None
            scan_all_files = None
    result = {"strategies": validate_strategies()}
    if scan_codebase:
        try:
            result["codebase"] = scan_codebase(root)
        except Exception as _e:
            result["codebase_error"] = str(_e)
    else:
        result["codebase_error"] = "router.scan_codebase not available"
    if scan_all_files:
        try:
            result["other_files"] = scan_all_files(root)
        except Exception as _e:
            result["other_files_error"] = str(_e)
    return result


if __name__ == "__main__":  # quick CLI for strategy + codebase checks
    try:
        import json as _json
        import sys

        root = sys.argv[1] if len(sys.argv) > 1 else "."
        print(_json.dumps(scan_project_with_model(root), indent=2))
    except Exception as _e:
        print(f"[strategy.scan] error: {_e}")
