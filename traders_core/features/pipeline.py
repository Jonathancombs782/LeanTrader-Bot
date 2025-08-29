from __future__ import annotations
import pandas as pd, numpy as np
from traders_core.utils.ta import rsi, atr

def rates_to_df(rates) -> pd.DataFrame:
    df = pd.DataFrame(rates)
    # MetaTrader5 returns 'time' in seconds since epoch (UTC)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.rename(columns={"real_volume":"volume"})
    if "volume" not in df: df["volume"] = df.get("tick_volume", 0)
    return df[["time","open","high","low","close","volume"]].set_index("time", drop=True)

def make_features(df: pd.DataFrame, rsi_window=14, atr_window=14, horizons=(3,6,12)):
    out = pd.DataFrame(index=df.index)
    px = df["close"]
    out["ret1"] = px.pct_change()
    out["vol20"] = out["ret1"].rolling(20).std()
    out["rsi"] = rsi(px, rsi_window)
    out["atr"] = atr(df, atr_window)
    out["mom20"] = px.pct_change(20)
    out["vwap20"] = (df["close"]*df["volume"]).rolling(20).sum() / (df["volume"].rolling(20).sum()+1e-9)
    for h in horizons:
        out[f"fwd_ret_{h}"] = px.shift(-h).pct_change(h)
    out = out.dropna()
    return out

def build_xy(feats: pd.DataFrame, horizon=6, thresh=0.0002):
    y = (feats[f"fwd_ret_{horizon}"] > thresh).astype(int)  # 1=long, 0=flat/short
    X = feats[["ret1","vol20","rsi","atr","mom20","vwap20"]]
    return X.dropna(), y.loc[X.index]
