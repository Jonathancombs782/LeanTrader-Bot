# volatility.py
from __future__ import annotations
import pandas as pd
import numpy as np
from typing import Dict

def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    if df.empty or not all(c in df for c in ("high","low","close")):
        return pd.Series([], dtype=float)
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=1).mean()

def bb_width(df: pd.DataFrame, n: int = 20, k: float = 2.0) -> pd.Series:
    if df.empty or "close" not in df:
        return pd.Series([], dtype=float)
    m = df["close"].rolling(n, min_periods=1).mean()
    s = df["close"].rolling(n, min_periods=1).std(ddof=0)
    upper, lower = m + k*s, m - k*s
    return (upper - lower) / m.replace(0, np.nan)

def vol_hot(df: pd.DataFrame, atr_th: float = 0.003, bbw_th: float = 0.02) -> Dict[str, float]:
    """Return latest ATR% and BBW and whether 'hot' >= thresholds."""
    if df.empty or "close" not in df:
        return {"atr_pct": 0.0, "bbw": 0.0, "hot": 0.0}
    a = atr(df, 14)
    bbw = bb_width(df, 20, 2.0)
    last_px = df["close"].iloc[-1]
    atr_pct = float((a.iloc[-1] / last_px) if last_px else 0.0)
    bbw_last = float(bbw.iloc[-1] if not bbw.empty else 0.0)
    hot = 1.0 if (atr_pct >= atr_th or bbw_last >= bbw_th) else 0.0
    return {"atr_pct": atr_pct, "bbw": bbw_last, "hot": hot}
