# bybit_smoke.py
from __future__ import annotations
import argparse, sys, time
from bybit_adapter import bybit_init, fetch_ohlcv, account_summary_lines, order_market

def parse_args():
    p = argparse.ArgumentParser(description="Bybit spot smoke test")
    p.add_argument("--symbol", default="DOGE/USDT", help="e.g. DOGE/USDT, BTC/USDT")
    p.add_argument("--timeframe", default="1m")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--dry_run", default="yes", help="yes|no")
    p.add_argument("--stake_usd", type=float, default=2.0, help="USD value to use for market order")
    p.add_argument("--side", default="buy", choices=["buy","sell"])
    return p.parse_args()

def main():
    args = parse_args()
    ex = bybit_init()
    print(f"Exchange: {ex.id} (type={ex.options.get('defaultType')})")

    # 1) balances (optional if no keys, it will error gracefully)
    for ln in account_summary_lines(ex):
        print(ln)

    # 2) candles (prefer safe wrapper)
    try:
        if hasattr(ex, 'safe_fetch_ohlcv'):
            try:
                rows = ex.safe_fetch_ohlcv(args.symbol, timeframe=args.timeframe, limit=args.limit)
            except Exception as e:
                print(f"[bybit_smoke] safe_fetch_ohlcv failed: {e}")
                rows = []
        else:
            try:
                rows = fetch_ohlcv(ex, args.symbol, args.timeframe, args.limit)
            except Exception as e:
                print(f"[bybit_smoke] fetch_ohlcv failed: {e}")
                rows = []
        print(f"Fetched {len(rows)} OHLCV for {args.symbol} {args.timeframe}")
    except Exception as e:
        print(f"OHLCV outer error: {e}")

    # 3) order (guarded by dry_run)
    if args.dry_run.lower() == "yes":
        print("[DRY RUN] Would place:", args.side, args.symbol, "stake_usd=", args.stake_usd)
        return

    print("Placing order...")
    res = order_market(ex, args.symbol, args.side, args.stake_usd)
    print("Result:", res)

if __name__ == "__main__":
    main()
