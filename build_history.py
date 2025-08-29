# build_history.py
import os
from research_optuna import build_history_ccxt, DATA_PATH

if __name__ == "__main__":
    ex = os.getenv("EXCHANGE_ID", "binanceus")
    sym = os.getenv("OPT_SYMBOL", os.getenv("SYMBOLS", "DOGE/USD").split(",")[0].strip())
    tf = os.getenv("TIMEFRAME", "1m")
    days = int(os.getenv("OPT_LOOKBACK_DAYS", "30"))
    df = build_history_ccxt(ex, sym, tf, days)
    print(f"Saved {len(df)} rows -> {DATA_PATH}")
    print(df.tail(3))
    print(df.head(3))
    