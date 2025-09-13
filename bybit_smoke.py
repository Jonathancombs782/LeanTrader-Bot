# bybit_smoke.py
from __future__ import annotations

import argparse

# Import bybit_adapter lazily inside main() so importing this module
# won't fail in environments without the adapter or network credentials.


def parse_args():
    p = argparse.ArgumentParser(description="Bybit spot smoke test")
    p.add_argument("--symbol", default="DOGE/USDT", help="e.g. DOGE/USDT, BTC/USDT")
    p.add_argument("--timeframe", default="1m")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--dry_run", default="yes", help="yes|no")
    p.add_argument("--stake_usd", type=float, default=2.0, help="USD value to use for market order")
    p.add_argument("--side", default="buy", choices=["buy", "sell"])
    return p.parse_args()


def main():
    args = parse_args()
    try:
        from bybit_adapter import account_summary_lines, bybit_init, fetch_ohlcv, order_market
    except Exception as e:
        print("[bybit_smoke] bybit_adapter not available:", e)
        return

    ex = bybit_init()
    # tolerate both raw ccxt exchange and router.ExchangeRouter
    try:
        ex_id = getattr(ex, "id", "")
        opts_src = getattr(ex, "options", None)
        if opts_src is None and hasattr(ex, "ex"):
            opts_src = getattr(ex.ex, "options", {})
        default_type = None
        if isinstance(opts_src, dict):
            default_type = opts_src.get("defaultType")
        print(f"Exchange: {ex_id} (type={default_type})")
    except Exception:
        try:
            print(f"Exchange: {getattr(ex, 'id', '<unknown>')}")
        except Exception:
            print("Exchange: <unknown>")

    # 1) balances (optional if no keys, it will error gracefully)
    for ln in account_summary_lines(ex):
        print(ln)

    # 2) candles (prefer safe wrapper)
    try:
        if hasattr(ex, "safe_fetch_ohlcv"):
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
        print(
            "[DRY RUN] Would place:",
            args.side,
            args.symbol,
            "stake_usd=",
            args.stake_usd,
        )
        return

    print("Placing order...")
    res = order_market(ex, args.symbol, args.side, args.stake_usd)
    print("Result:", res)


if __name__ == "__main__":
    main()
