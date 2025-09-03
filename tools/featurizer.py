"""Minimal multi-timeframe featurizer.

Reads a CSV produced by market_data.fetch_ohlcv and produces a feature matrix X and
labels y (next-bar direction) suitable for quick testing with scikit-learn.
"""
from __future__ import annotations

import pandas as pd
from pathlib import Path
from typing import Tuple, List


def load_csv(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(p)
    # ensure columns
    df = df.rename(columns={c: c.strip() for c in df.columns})
    return df


def featurize_basic(df: pd.DataFrame) -> pd.DataFrame:
    # expect columns: ts, open, high, low, close, vol
    df = df.copy()
    df["ret"] = df["close"].pct_change().fillna(0)
    df["range"] = (df["high"] - df["low"]) / df["open"].replace(0, 1)
    df["logvol"] = (df["vol"].replace(0, 1)).apply(lambda x: float(x)).fillna(0)
    df["ma3"] = df["close"].rolling(3).mean().fillna(df["close"])
    df["ma10"] = df["close"].rolling(10).mean().fillna(df["close"])
    df["ma_diff"] = df["ma3"] - df["ma10"]
    return df


def build_features_and_labels(path: str, lookahead: int = 1) -> Tuple[pd.DataFrame, pd.Series]:
    df = load_csv(path)
    df = featurize_basic(df)
    # label: next close > current close -> 1 else 0
    df["next_close"] = df["close"].shift(-lookahead)
    df = df.dropna()
    X = df[["ret", "range", "logvol", "ma3", "ma10", "ma_diff"]].astype(float)
    y = (df["next_close"] > df["close"]).astype(int)
    return X, y


def sample_paths_from_data_dir(data_dir: str, pattern: str = "*_BTC_USDT_1m.csv") -> List[str]:
    p = Path(data_dir)
    if not p.exists():
        return []
    return [str(x) for x in p.glob(pattern)]
