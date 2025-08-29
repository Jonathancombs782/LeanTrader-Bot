# indicators.py
from __future__ import annotations
import numpy as np
import pandas as pd

def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def atr(df: pd.DataFrame, n: int=14) -> pd.Series:
    h,l,c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h-l), (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def rsi(s: pd.Series, n: int=14) -> pd.Series:
    d = s.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0,np.nan)
    return 100 - 100/(1+rs)

def macd(s: pd.Series, fast=12, slow=26, sig=9):
    macd = ema(s, fast) - ema(s, slow)
    signal = ema(macd, sig)
    hist = macd - signal
    return macd, signal, hist

def supertrend(df: pd.DataFrame, period=10, mult=3.0) -> pd.Series:
    # simple supertrend direction: True=up, False=down
    hl2 = (df["high"] + df["low"]) / 2.0
    atrv = atr(df, period)
    upper = hl2 + mult * atrv
    lower = hl2 - mult * atrv
    dir_up = pd.Series(False, index=df.index)
    # naive regime from price vs bands
    dir_up = df["close"] > upper.shift(1)
    dir_dn = df["close"] < lower.shift(1)
    regime = dir_up.astype(int) - dir_dn.astype(int)
    return (regime >= 0)
# indicators.py