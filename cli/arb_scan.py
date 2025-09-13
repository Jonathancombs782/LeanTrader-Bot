from __future__ import annotations

import argparse
import json

from scanners.arbitrage import cross_exchange_spreads, record_arb_opp


def main():
    p = argparse.ArgumentParser(description="Cross-exchange arbitrage scanner")
    p.add_argument("--symbols", required=True, help="comma-separated symbols, e.g., BTC/USDT,ETH/USDT")
    p.add_argument("--venues", required=True, help="comma-separated venues, e.g., binance,kraken,coinbase")
    p.add_argument("--min_bps", type=float, default=10.0)
    args = p.parse_args()

    symbols = [s.replace(" ", "").replace(",", "/") if "/" not in s else s for s in args.symbols.split(",")]
    venues = [v.strip() for v in args.venues.split(",") if v.strip()]
    opps = cross_exchange_spreads(symbols, venues, min_bps=float(args.min_bps))
    if opps:
        record_arb_opp(len(opps))
    print(json.dumps({"opportunities": opps}))


if __name__ == "__main__":
    main()

