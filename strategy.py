# strategy.py
from __future__ import annotations
import os, json, math
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
    tr = pd.concat([(high-low), (high-prev).abs(), (low-prev).abs()], axis=1).max(axis=1)
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
    def __init__(self, ema_fast=50, ema_slow=200, bb_period=20, bb_std=2.0,
                 bb_bw_lookback=120, bb_bw_quantile=0.5, atr_period=14):
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
        d["bb_thresh"] = d["bb_bw"].rolling(self.bb_bw_lookback)\
            .quantile(self.bb_bw_quantile, interpolation="nearest")
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
    sr_lookback: int = 60         # lookback for swing S/R
    pin_len_mult: float = 1.5     # how long wick vs body
    engulf_body_mult: float = 1.1 # engulf body strength
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
        d["sr_low"]  = _roll_min(d["low"],  self.sr_lookback).shift(1)

        # Pin bar long: long lower wick, small body, close>open (or close near high)
        pin_long = (d["wb"] > self.pin_len_mult * d["body"]) & (d["close"] > d["open"])
        near_sr   = (d["low"] <= d["sr_low"] * 1.002)  # touched/near support

        # Bullish engulfing near support
        prev_body = d["body"].shift(1)
        engulf = (d["close"] > d["open"]) & (prev_body > 0) & \
                 ((d["close"] - d["open"]) > self.engulf_body_mult * prev_body) & \
                 (d["open"] <= d["close"].shift(1))

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
            strat_name = data.get("strategy", "trend")
            params = data.get("params", {})
            strat = get_strategy(strat_name, **params)
            return strat, params
        except Exception as e:
            print("[strategy] failed to load best params:", e)

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
