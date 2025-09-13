# analyzer.py
from __future__ import annotations

import numpy as np
import pandas as pd


def instant_analysis(df: pd.DataFrame, symbol: str) -> str:
    if df is None or df.empty:
        return f"{symbol}: no data"
    closes = pd.Series(df["close"])
    ret5 = (closes.iloc[-1] / closes.iloc[-5] - 1.0) if len(closes) >= 5 else 0.0
    rng = (df["high"].tail(20).max() - df["low"].tail(20).min()) / (closes.iloc[-1] + 1e-12)
    heat = np.tanh(5 * rng)
    return f"{symbol} | 5-bar return={ret5:+.3%} | heat={heat:.2f}"
