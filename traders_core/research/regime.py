from __future__ import annotations
import pandas as pd
import numpy as np

def tag_regimes(px: pd.Series, vol_window: int, calm_quantile: float = 0.4) -> pd.Series:
    ret1 = px.pct_change()
    vol = ret1.rolling(vol_window).std()
    thresh = vol.quantile(calm_quantile)
    reg = np.where(vol <= thresh, "calm", "storm")
    return pd.Series(reg, index=px.index)
