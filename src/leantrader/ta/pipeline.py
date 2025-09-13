from __future__ import annotations

import os
from typing import Dict

import numpy as np
import pandas as pd


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=int(max(1, n)), adjust=False).mean()


def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(int(max(1, n))).mean()


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    rs = up / (dn.replace(0, np.nan))
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    tr = pd.concat(
        [(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(n).mean()


def _bollinger(close: pd.Series, n: int = 20) -> pd.DataFrame:
    ma = close.rolling(n).mean()
    sd = close.rolling(n).std(ddof=0)
    upper = ma + 2 * sd
    lower = ma - 2 * sd
    bw = (upper - lower) / ma.replace(0, np.nan)
    return pd.DataFrame({"bb_mid": ma, "bb_up": upper, "bb_dn": lower, "bb_bw": bw})


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    f = _ema(close, fast)
    s = _ema(close, slow)
    macd = f - s
    sig = _ema(macd, signal)
    hist = macd - sig
    return pd.DataFrame({"macd": macd, "macd_sig": sig, "macd_hist": hist})


def _obv(close: pd.Series, vol: pd.Series) -> pd.Series:
    direction = np.sign(close.diff().fillna(0))
    return (direction * vol.fillna(0)).cumsum()


def _stochastic(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14, smooth: int = 3) -> pd.DataFrame:
    ll = low.rolling(n).min()
    hh = high.rolling(n).max()
    k = 100 * (close - ll) / (hh - ll).replace(0, np.nan)
    d = k.rolling(smooth).mean()
    return pd.DataFrame({"stoch_k": k, "stoch_d": d})


def _supertrend(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 10, mult: float = 3.0) -> pd.Series:
    atr = _atr(high, low, close, n)
    hl2 = (high + low) / 2.0
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr
    st = pd.Series(index=close.index, dtype=float)
    trend = True  # True=uptrend
    prev = np.nan
    for i in range(len(close)):
        if i == 0:
            st.iloc[i] = upper.iloc[i]
            prev = st.iloc[i]
            continue
        if close.iloc[i] > prev:
            trend = True
        elif close.iloc[i] < prev:
            trend = False
        st.iloc[i] = lower.iloc[i] if trend else upper.iloc[i]
        prev = st.iloc[i]
    return st


def _vwap(df: pd.DataFrame) -> pd.Series:
    # Requires volume
    if "volume" not in df.columns:
        return pd.Series(index=df.index, dtype=float)
    pv = (df["close"] * df["volume"]).cumsum()
    vv = df["volume"].cumsum().replace(0, np.nan)
    return pv / vv


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        s = out[c]
        if s.dtype.kind in ("i", "u", "f"):
            m = s.rolling(100).mean()
            v = s.rolling(100).std(ddof=0).replace(0, np.nan)
            out[c] = (s - m) / v
    return out


def _asof_join(frames: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    # Align multiple TF frames by asof join on index
    keys = sorted(frames.keys())
    base_key = keys[0]
    base = frames[base_key].copy()
    out = base.copy()
    for k in keys[1:]:
        df = frames[k].copy()
        df = df.add_suffix(f"_{k}")
        out = pd.merge_asof(out.sort_index(), df.sort_index(), left_index=True, right_index=True, direction="backward")
    return out


def compute_ta(frames: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Compute multi-timeframe technical features from input OHLCV frames.

    frames keys are TF codes like "M1","M5","M15","M30","H1","H4","D1".
    Each DataFrame must have columns: open, high, low, close (volume optional).
    """
    # per-TF indicator computation
    feats: Dict[str, pd.DataFrame] = {}
    for k, df in frames.items():
        d = df.copy()
        d = d.sort_index()
        close = d["close"].astype(float)
        high = d["high"].astype(float)
        low = d["low"].astype(float)
        vol = d.get("volume", pd.Series(index=d.index, dtype=float))
        out = pd.DataFrame(index=d.index)
        out["ema_20"] = _ema(close, 20)
        out["ema_50"] = _ema(close, 50)
        out["sma_50"] = _sma(close, 50)
        out["sma_200"] = _sma(close, 200)
        out["rsi_14"] = _rsi(close, 14)
        atr14 = _atr(high, low, close, 14)
        out["atr_14"] = atr14
        bb = _bollinger(close, 20)
        out = out.join(bb)
        macd = _macd(close)
        out = out.join(macd)
        out["obv"] = _obv(close, vol)
        stoch = _stochastic(high, low, close, 14, 3)
        out = out.join(stoch)
        out["supertrend"] = _supertrend(high, low, close, 10, 3.0)
        out["vwap"] = _vwap(d)
        # candle tags (simple)
        out["candle_up"] = (close > close.shift()).astype(int)
        out["candle_body"] = (close - d["open"]).abs()
        feats[k] = out

    # normalize within each TF (optional)
    if os.getenv("TA_NORMALIZE", "true").lower() in ("1", "true", "yes"):
        feats = {k: _normalize(v) for k, v in feats.items()}

    # suffix and join by asof
    suffixed = {k: v.add_suffix(f"_{k}") for k, v in feats.items()}
    out = _asof_join(suffixed)
    out = out.dropna(how="all")
    return out
