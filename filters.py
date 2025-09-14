# filters.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import pandas as pd


@dataclass
class EventRiskFilter:
    """Blocks entries when risk_off flags are active (e.g., high-impact events)."""

    col: str = "risk_off_calendar"

    def allow(self, row: Dict) -> bool:
        v = row.get(self.col, 0)
        return int(v) == 0


@dataclass
class SpreadVolFilter:
    """Blocks if ATR relative to price is too high (wild) or too low (dead)."""

    atr_col: str = "atr"
    close_col: str = "close"
    min_ratio: float = 0.0003
    max_ratio: float = 0.03

    def allow(self, row: Dict) -> bool:
        atr = float(row.get(self.atr_col, 0.0))
        px = float(row.get(self.close_col, 0.0))
        if px <= 0:
            return False
        r = atr / px
        return (r >= self.min_ratio) and (r <= self.max_ratio)


@dataclass
class SentimentGate:
    """Blocks (or requires) certain sentiment direction."""

    col: str = "news_sent"
    min_score: float = -1.0  # allow all by default
    max_score: float = 1.0

    def allow(self, row: Dict) -> bool:
        s = float(row.get(self.col, 0.0))
        return (s >= self.min_score) and (s <= self.max_score)


# ---------- Multi-timeframe ensemble ----------
def resample_for_tf(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    rule = {
        "1m": "1T",
        "3m": "3T",
        "5m": "5T",
        "15m": "15T",
        "30m": "30T",
        "1h": "1H",
    }.get(tf, "1T")
    out = (
        df.set_index("timestamp")
        .resample(rule)
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "vol": "sum",
            }
        )
        .dropna()
        .reset_index()
    )
    return out


def vote_long_signal(signals: Dict[str, pd.DataFrame]) -> pd.Series:
    """signals: tf -> df_with_long_signal; returns aligned 1m votes."""
    # align on the smallest TF index
    base_tf = sorted(
        signals.keys(),
        key=lambda x: {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1h": 60}.get(
            x, 999
        ),
    )[0]
    base = signals[base_tf].set_index("timestamp")
    votes = pd.DataFrame(index=base.index)
    for tf, d in signals.items():
        s = d.set_index("timestamp")["long_signal"].astype(int)
        s = s.reindex(votes.index, method="ffill").fillna(0)
        votes[tf] = s
    return (votes.sum(axis=1) >= max(2, int(0.6 * len(signals)))).astype(
        int
    )  # majority (>=60%) vote
