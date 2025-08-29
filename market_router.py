# market_router.py
from __future__ import annotations
import pandas as pd
import numpy as np

def _trend_score(df: pd.DataFrame) -> float:
    if len(df) < 60: return 0.0
    ret = pd.Series(df["close"]).pct_change().tail(60).fillna(0.0)
    z = ret.mean() / (ret.std(ddof=0) + 1e-12)
    return float(np.tanh(2.5 * z))

def select_markets(ex, symbols, timeframe, strat, risk_dict, top_k=3, mtf_list=None):
    """
    For each symbol: fetch candles, compute signals, assign a score.
    Return top_k list of dicts: {"symbol", "df", "score"}.
    """
    out = []
    for sym in symbols:
        try:
            # Use router safe wrapper
            rows = ex.safe_fetch_ohlcv(sym, timeframe=timeframe, limit=400)
            if not rows: 
                continue
            df = pd.DataFrame(rows, columns=["ts","open","high","low","close","vol"])
            df["timestamp"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
            score = _trend_score(df)
            out.append({"symbol": sym, "df": df, "score": score})
        except Exception:
            continue
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[: max(1, int(top_k))]
