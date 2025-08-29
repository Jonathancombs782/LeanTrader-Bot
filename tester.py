# tester.py
from __future__ import annotations
import pandas as pd, numpy as np
from pathlib import Path
from alpha_engines import ensemble_long_signal

def evaluate(df: pd.DataFrame):
    gate, score = ensemble_long_signal(df, 0.72)
    longs = gate.shift(1) & ~gate.shift(2).fillna(False)  # new signals
    ret = df["close"].pct_change().fillna(0)
    pnl = (ret * longs.astype(int)).cumsum()
    return pnl.iloc[-1], score.iloc[-200:].mean()

# Usage:
# df must have columns: open,high,low,close,vol
if __name__ == "__main__":
    p = Path("data/EURUSD_1m_2020-2023.csv")
    df = pd.read_csv(p, parse_dates=["timestamp"])
    final_pnl, avg_score = evaluate(df)
    print(f"Final PnL: {final_pnl:.4f}, Avg Score (last 200): {avg_score:.4f}")
    