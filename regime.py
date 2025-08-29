# regime.py
from __future__ import annotations
import pandas as pd
import numpy as np

def detect_regime(df_feat: pd.DataFrame) -> str:
    """
    Simple regime tag based on Bollinger bandwidth + EMA slope.
    Returns: 'trend' or 'chop'
    """
    d = df_feat
    if "bb_bw" in d and "ema_fast" in d:
        last_bw = float(d["bb_bw"].iloc[-1])
        ema_slope = float(d["ema_fast"].iloc[-1] - d["ema_fast"].iloc[-5])
        if last_bw > 0.02 and abs(ema_slope) > 0.0:
            return "trend"
    return "chop"
# regime.py