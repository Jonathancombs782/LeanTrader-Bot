"""Simple diagnostic to probe multiple exchanges for OHLCV access.

Writes a small run log to runtime/logs/market_diag.txt so results are persistent.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import List

from tools.market_data import fetch_ohlcv_multi


def _write_log(lines: List[str]) -> None:
    p = Path("runtime") / "logs" / "market_diag.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for l in lines:
            f.write(l + "\n")


def main() -> int:
    exchanges = ["bybit", "gateio", "kucoin", "binance", "okx"]
    symbol = "BTC/USDT"
    tf = "1m"
    results: List[str] = []
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    results.append(f"market_diag start {ts}")
    for ex in exchanges:
        try:
            used, rows = fetch_ohlcv_multi([ex], symbol, timeframe=tf, limit=50)
            results.append(f"{ex}: ok, rows={len(rows)}")
        except Exception as e:
            results.append(f"{ex}: FAILED: {e}")
    ts2 = time.strftime("%Y-%m-%d %H:%M:%S")
    results.append(f"market_diag done {ts2}")
    _write_log(results)
    for r in results:
        print(r)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
