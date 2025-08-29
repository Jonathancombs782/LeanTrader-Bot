# mt5_single_shot.py
from __future__ import annotations

import argparse
from typing import Dict, Any, Optional
import numpy as np

from mt5_adapter import (
    mt5_init, bars_df, account_summary_lines,
    min_stop_distance_points, order_send_market,
)

def atr(series: np.ndarray, n: int = 14) -> float:
    if len(series) < n + 1:
        return 0.0
    # simple ATR approximation with close[-1] range
    highs = series["high"]
    lows = series["low"]
    closes = series["close"]
    prev = np.r_[closes[:-1], closes[-1]]
    tr = np.maximum(highs - lows, np.maximum(np.abs(highs - prev), np.abs(lows - prev)))
    return float(np.nanmean(tr[-n:]))

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--timeframe", required=True, help="M1 M5 M15 M30 H1 H4 D1")
    ap.add_argument("--side", required=True, choices=["buy", "sell"])
    ap.add_argument("--lots", type=float, required=True)

    ap.add_argument("--dry_run", default="no", help="yes|no")
    ap.add_argument("--print_bars", type=int, default=5)

    # Choose one: points OR ATR multiplier (fallback)
    ap.add_argument("--sl_tp_pts", type=float, default=None,
                    help="If set, use this many points for both SL/TP (symmetric).")
    ap.add_argument("--atr_mult", type=float, default=2.0,
                    help="Used if sl_tp_pts not provided.")
    args = ap.parse_args()

    mt5_init()

    print("\n".join(account_summary_lines()))

    # Fetch bars for SL/TP sizing
    df = bars_df(args.symbol, args.timeframe, limit=200)
    if df.empty:
        print("[warn] bars_df returned empty DataFrame")
        return
    if args.print_bars > 0:
        tail = df.tail(args.print_bars)
        print("\nTail (last bars):")
        try:
            print(tail.to_string(index=False))
        except Exception:
            print(tail)

    last = float(df["close"].iloc[-1])

    # Compute SL/TP distances
    pts_min = min_stop_distance_points(args.symbol)
    if args.sl_tp_pts is not None:
        pts = max(float(args.sl_tp_pts), float(pts_min))
    else:
        # ATR-based distance converted to points
        a = atr(df[["high","low","close"]].to_records(index=False), 14)
        pts = max(float(round(a / (last * 0.0001))), float(pts_min))  # rough: convert price ATR to points

    # Convert points -> price
    pt_value = 0.0001  # for most FX majors; for metals/indices adjust if needed
    dist_px = pts * pt_value

    if args.side == "buy":
        sl = last - dist_px
        tp = last + dist_px
    else:
        sl = last + dist_px
        tp = last - dist_px

    print(f"\nRequest: {args.side.upper()} {args.symbol} lots={args.lots} "
          f"entry~{last:.5f} SL~{sl:.5f} TP~{tp:.5f}  (min_dist_pts={pts_min}, used_pts={pts:.0f})")

    if args.dry_run.lower() == "yes":
        print("[dry-run] not sending order.")
        return

    # SEND
    res: Dict[str, Any] = order_send_market(
        symbol=args.symbol,
        side=args.side,
        lots=args.lots,
        sl=sl,
        tp=tp,
        deviation=20,
    )
    print("retcode:", res.get("retcode"), "comment:", res.get("comment"),
          "deal:", res.get("deal"), "order:", res.get("order"))
    if res.get("request"):
        print("request:", res["request"])


if __name__ == "__main__":
    main()
