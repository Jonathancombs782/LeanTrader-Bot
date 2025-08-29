# mt5_smoke.py  — drop-in replacement
from __future__ import annotations

import sys
import pandas as pd  # only used to pretty-print the last few rows

# Use the adapter we already wired
from mt5_adapter import mt5_init, account_summary_lines, bars_df


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python mt5_smoke.py EURUSD M5")
        return

    symbol = sys.argv[1]
    timeframe = sys.argv[2]

    # 1) Initialize MT5 from .env and keep the handle
    m = mt5_init()
    print("✅ initialize OK")

    # 2) Account summary (balance/equity/positions)
    for line in account_summary_lines():
        print(line)

    # 3) Pull some bars to prove market data works
    df: pd.DataFrame = bars_df(symbol, timeframe, limit=50)
    if df.empty:
        print(f"No bars returned for {symbol} {timeframe}")
        return

    last_close = float(df["close"].iloc[-1])
    print(f"\nFetched {len(df)} bars for {symbol} {timeframe}. Last close={last_close:.5f}")

    # Optional: show current open positions using the MT5 handle
    try:
        pos = m.positions_get() or []
        print(f"Positions: {len(pos)}")
        for p in pos[:5]:
            try:
                d = p._asdict()
                print(f" - {d.get('symbol')} lots={d.get('volume')} pnl={d.get('profit')}")
            except Exception:
                print(f" - {p}")
    except Exception as e:
        print(f"positions_get error: {e}")

    # Optional: pretty print the tail
    try:
        print("\nTail (last 5 bars):")
        print(df.tail(5).to_string(index=False))
    except Exception:
        pass


if __name__ == "__main__":
    main()
