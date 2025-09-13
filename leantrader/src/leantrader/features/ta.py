import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    delta = s.diff()
    up, down = (delta.clip(lower=0), -delta.clip(upper=0))
    rs = up.rolling(n).mean() / down.rolling(n).mean().replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    plus_dm = (high.diff()).clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    tr = pd.concat([(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(n).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / n, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / n, adjust=False).mean() / atr)
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan)
    return dx.rolling(n).mean()


def fvg_score(df: pd.DataFrame, lookback: int = 3) -> pd.Series:
    high, low = df["high"], df["low"]
    gap_up = (low.shift(1) > high.shift(2)).astype(int)
    gap_dn = (high.shift(1) < low.shift(2)).astype(int)
    return (gap_up - gap_dn).rolling(lookback).sum().fillna(0)
