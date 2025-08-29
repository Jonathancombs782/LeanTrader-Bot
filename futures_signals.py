# futures_signals.py
from __future__ import annotations
from typing import Dict, Any
import pandas as pd

def ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()

def fut_side_from_ema(df: pd.DataFrame) -> str | None:
    if df.empty or "close" not in df or len(df) < 30:
        return None
    c = df["close"]
    e12, e26 = ema(c, 12), ema(c, 26)
    up = e12.iloc[-1] > e26.iloc[-1] and e12.iloc[-2] <= e26.iloc[-2]
    dn = e12.iloc[-1] < e26.iloc[-1] and e12.iloc[-2] >= e26.iloc[-2]
    if up: return "buy"
    if dn: return "sell"
    return None

def calc_contract_qty_usdt(px: float, usd_stake: float, leverage: float, min_qty: float = 0.001, step: float = 0.001) -> float:
    """
    Linear (USDT) perps: qty is base-coin size. Approx qty = (usd * leverage) / price.
    """
    if px <= 0: return 0.0
    raw = (usd_stake * leverage) / px
    # round to step & min
    steps = max(1, int(raw / step))
    q = steps * step
    return max(q, min_qty)
