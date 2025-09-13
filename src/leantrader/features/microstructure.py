import pandas as pd

from .ta import adx, fvg_score, rsi


def engineer(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["rsi_14"] = rsi(out["close"], 14)
    out["adx_14"] = adx(out, 14)
    out["fvg_score"] = fvg_score(out, 3)
    out["ms_state"] = "flat"
    swing_up = (out["high"] > out["high"].shift(1)) & (out["low"] > out["low"].shift(1))
    swing_dn = (out["high"] < out["high"].shift(1)) & (out["low"] < out["low"].shift(1))
    out.loc[swing_up, "ms_state"] = "bull"
    out.loc[swing_dn, "ms_state"] = "bear"
    out["rsi_div"] = (out["close"].diff() < 0).astype(int) * ((out["rsi_14"].diff() > 0).astype(int)) - (
        out["close"].diff() > 0
    ).astype(int) * ((out["rsi_14"].diff() < 0).astype(int))
    return out
