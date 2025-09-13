"""Safe smoke-test for trading flow.

This script forces the router into `paper` backend and attempts a sample order.
It writes a persistent log to `runtime/logs/smoke_trade.txt` showing the results.
"""

from __future__ import annotations

import os
import time
import traceback
from pathlib import Path


def _write(lines: list[str]) -> None:
    p = Path("runtime") / "logs" / "smoke_trade.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def main() -> int:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = [f"smoke_trade start {ts}"]
    try:
        # Force paper backend to ensure no live orders are sent
        os.environ["EXCHANGE_ID"] = "paper"
        os.environ["PAPER_START_CASH"] = os.environ.get("PAPER_START_CASH", "10000")

        # import ExchangeRouter from router
        from router import ExchangeRouter

        r = ExchangeRouter()
        lines.append(f"router.info: {r.info()}")

        # attempt a dry-run order (paper broker will simulate)
        sym = "BTC/USDT"
        res = r.safe_place_order(sym, "buy", 0.001, price=100.0)
        lines.append(f"order result: {res}")

        # check balance snapshot if available
        bal = r.safe_fetch_balance()
        lines.append(f"balance snapshot keys: {list(bal.keys()) if isinstance(bal, dict) else str(type(bal))}")

    except Exception as e:
        lines.append(f"smoke failed: {e}")
        lines.append(traceback.format_exc())

    ts2 = time.strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"smoke_trade done {ts2}")
    _write(lines)
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
