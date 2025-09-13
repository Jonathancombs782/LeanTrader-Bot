import argparse
import os
import time

import pandas as pd

from .live.signal_service import generate_signals


def csv_path(pair: str, tf: str) -> str:
    p = pair.replace("/", "")
    return f"data/ohlc/{p}_{tf}.csv"


def load_frames(pair: str):
    frames = {}
    for tf in ["D1", "H4", "H1", "M15"]:
        fp = csv_path(pair, tf)
        if os.path.exists(fp):
            df = pd.read_csv(fp, parse_dates=["time"], index_col="time")
            frames[tf] = df[["open", "high", "low", "close"]].sort_index()
    return frames


def main():
    ap = argparse.ArgumentParser(description="LeanTrader CLI")
    ap.add_argument("--pair", default="EURUSD")
    ap.add_argument("--loop", action="store_true", help="poll and send signals when they fire")
    ap.add_argument("--sleep", type=int, default=60, help="polling seconds")
    args = ap.parse_args()
    frames = load_frames(args.pair)
    if not frames:
        print("No data found. Put CSVs in data/ohlc/<PAIR>_<TF>.csv with columns: time,open,high,low,close")
        return
    if args.loop:
        last_idx = None
        while True:
            frames = load_frames(args.pair)
            sigs = generate_signals(frames, args.pair)
            if len(sigs) and sigs.index[-1] != last_idx:
                last_idx = sigs.index[-1]
            time.sleep(args.sleep)
    else:
        sigs = generate_signals(frames, args.pair)
        print(sigs.tail())


if __name__ == "__main__":
    main()
