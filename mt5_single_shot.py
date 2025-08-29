# mt5_single_shot.py
from __future__ import annotations

import argparse
from typing import Optional, Dict, Any

from mt5_adapter import (
    mt5_init,
    account_summary_lines,
    bars_df,
    order_send_market,
)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Place a single MT5 market order (demo-safe)")
    ap.add_argument("--symbol", required=True, help="e.g. EURUSD, XAUUSD")
    ap.add_argument("--timeframe", default="M5", help="M1,M5,M15,M30,H1,H4,D1,W1,MN1")
    ap.add_argument("--side", choices=["buy", "sell"], required=True)
    ap.add_argument("--lots", type=float, default=0.01)

    ap.add_argument("--dry_run", default="no", help="yes/no — if yes, only prints the request")
    # Optional explicit SL/TP prices (skip to let broker accept 0.0)
    ap.add_argument("--sl", type=float, default=None)
    ap.add_argument("--tp", type=float, default=None)

    return ap.parse_args()


def print_tail(symbol: str, timeframe: str) -> None:
    try:
        df = bars_df(symbol, timeframe, limit=50)
        tail = df.tail(5)
        want = ["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]
        cols = [c for c in want if c in tail.columns]
        print("\nTail (last bars):")
        if tail.empty or not cols:
            print("(no bars to display)")
        else:
            print(tail[cols].to_string(index=False))
    except Exception as e:
        print(f"[warn] bars df error: {e}")


def main() -> None:
    args = parse_args()

    mt5 = mt5_init()
    for line in account_summary_lines():
        print(line)

    print_tail(args.symbol, args.timeframe)

    # Build and (optionally) send order
    print("\nRequest:", end=" ")
    print(f"{args.side.upper()} {args.symbol} lots={args.lots:.2f} "
          f"SL={args.sl or '-'}  TP={args.tp or '-'}")

    if str(args.dry_run).lower() in ("yes", "y", "true", "1"):
        print("[dry-run] not sending order.")
        return

    res: Dict[str, Any] = order_send_market(
        symbol=args.symbol,
        side=args.side,
        lots=args.lots,
        sl=args.sl,
        tp=args.tp,
        deviation=20,
    )

    print("request:", res.get("request"))
    print("retcode:", res.get("retcode"), "comment:", res.get("comment"),
          "deal:", res.get("deal"), "order:", res.get("order"))


if __name__ == "__main__":
    main()
