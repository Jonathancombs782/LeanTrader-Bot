from __future__ import annotations

import argparse
import json
import random
import time

from scanners.arbitrage import plan_and_route


def main():
    p = argparse.ArgumentParser(description="Simulate arbitrage execution and record latency")
    p.add_argument("--buy", required=True, help="buy venue")
    p.add_argument("--sell", required=True, help="sell venue")
    p.add_argument("--symbol", required=True, help="symbol, e.g., BTC/USDT")
    p.add_argument("--qty", type=float, default=0.01)
    args = p.parse_args()

    opp = {"buy_venue": args.buy, "sell_venue": args.sell, "symbol": args.symbol, "size_cap": args.qty}
    plan = plan_and_route(opp, args.qty)
    # simulate execution latency and record into ARB_FILL_MS
    try:
        from scanners.arbitrage import ARB_FILL_MS
        if ARB_FILL_MS is not None:
            t0 = time.time()
            # simulate per-leg latency
            for leg in plan.get("plan", []):
                time.sleep(random.uniform(0.01, 0.05))
            dt_ms = (time.time() - t0) * 1000.0
            ARB_FILL_MS.observe(float(dt_ms))
    except Exception:
        pass
    print(json.dumps(plan))


if __name__ == "__main__":
    main()

