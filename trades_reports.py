# trades_report.py
from __future__ import annotations
import argparse, sys
from datetime import datetime, timedelta, timezone
import pandas as pd
from ledger import LEDGER, daily_pnl_text

def _load() -> pd.DataFrame:
    try:
        return pd.read_csv(LEDGER)
    except Exception:
        return pd.DataFrame()

def _since_days(df: pd.DataFrame, days: int) -> pd.DataFrame:
    if df.empty: return df
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return df[df["date"] >= cutoff.replace(tzinfo=None)]

def main():
    p = argparse.ArgumentParser(description="Ledger stats")
    p.add_argument("--last", type=int, default=7, help="days back")
    p.add_argument("--daily", action="store_true", help="print today’s daily summary")
    args = p.parse_args()

    if args.daily:
        print(daily_pnl_text())
        return

    df = _load()
    if df.empty:
        print("No trades yet.")
        return

    sub = _since_days(df, args.last)
    if sub.empty:
        print(f"No trades in the last {args.last} day(s).")
        return

    closed = sub[sub["status"] != "open"]
    n = len(closed)
    wr = (closed["pnl_raw"] > 0).mean() * 100 if n else 0.0
    gross = float(closed["pnl_raw"].sum())
    rsum  = float(closed["pnl_r"].sum())

    print(f"Window: last {args.last} day(s)")
    print(f"Closed trades: {n} | Winrate: {wr:.1f}%")
    print(f"Gross PnL: {gross:.4f} (quote) | Sum R: {rsum:.2f}")

    # per-symbol
    by_sym = closed.groupby("symbol")["pnl_raw"].sum().sort_values(ascending=False).head(10)
    if not by_sym.empty:
        print("\nTop symbols (PnL):")
        for sym, v in by_sym.items():
            print(f"  {sym:<10} {v:.4f}")

if __name__ == "__main__":
    main()
