"""Demo: fetch a small OHLCV sample and run the trainer.

Usage: python tools/run_demo_train.py

This script is conservative: it only reads public market data and trains locally.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

from market_data import fetch_ohlcv

try:
    from trainer import train_dummy_classifier
except Exception:
    train_dummy_classifier = None


def main():
    try:
        print("fetching OHLCV from binance BTC/USDT (1m, limit=200) ...")
        rows = fetch_ohlcv("binance", "BTC/USDT", timeframe="1m", limit=200)
        if not rows:
            print("no rows fetched; aborting")
            return 1
        csv_path = Path("runtime") / "data" / "binance_BTC_USDT_1m.csv"
        if not csv_path.exists():
            print("expected CSV not found after fetch; aborting")
            return 1
        print(f"fetched and persisted CSV: {csv_path}")
        if train_dummy_classifier is None:
            print("scikit-learn not available; skipping training")
            return 0
        print("running trainer...")
        out = train_dummy_classifier(str(csv_path))
        print("training result:", out)
        return 0
    except Exception:
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
