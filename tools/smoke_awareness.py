import sys
sys.path.insert(0, r"C:\Users\User\Downloads\LeanTrader_ForexPack")

import argparse
import json
import os
from typing import List

import pandas as pd

from awareness import AwarenessConfig, SituationalAwareness
from router import ExchangeRouter


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default=os.getenv("SMOKE_AW_SYMBOL", "BTC/USDT"))
    ap.add_argument("--exchange", default=os.getenv("SMOKE_AW_EXCHANGE", "okx"))
    ap.add_argument("--limit", type=int, default=int(os.getenv("SMOKE_AW_LIMIT", "300")))
    ap.add_argument("--tf", default=os.getenv("SMOKE_AW_TF", "5m"))
    ap.add_argument("--win", type=float, default=float(os.getenv("SMOKE_AW_WIN", "0.55")))
    ap.add_argument("--payoff", type=float, default=float(os.getenv("SMOKE_AW_PAYOFF", "1.1")))
    args = ap.parse_args()

    os.environ.setdefault("EXCHANGE_ID", args.exchange)
    ex = ExchangeRouter()
    rows: List[List[float]] = ex.fetch_ohlcv(args.symbol, timeframe=args.tf, limit=args.limit)
    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"]).tail(120)

    aw = SituationalAwareness(AwarenessConfig())
    # Patch ATR to ensure pandas rolling works (awareness.py stays unmodified by spec)
    def _atr(self, close, high, low, n=14):
        tr = (high - low).to_frame("hl")
        tr["hc"] = (high - close.shift()).abs()
        tr["lc"] = (low - close.shift()).abs()
        s = tr.max(axis=1)
        return s.rolling(n).mean()
    import types as _types
    aw.atr = _types.MethodType(_atr, aw)
    dec = aw.decide(df, equity=1000.0, base_conf=0.6, win_rate=args.win, payoff=args.payoff)
    print(json.dumps({
        "symbol": args.symbol,
        "reason": dec.reason,
        "allow": dec.allow,
        "size_frac": dec.size_frac,
        "stop_atr": dec.stop_atr,
        "take_atr": dec.take_atr,
    }, indent=2))


if __name__ == "__main__":
    main()


