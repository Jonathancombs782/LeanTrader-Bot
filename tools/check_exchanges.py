"""Check availability for a set of exchanges and write a status log.

Writes `runtime/logs/exchanges_status.txt` with per-exchange results. Use
`python -m tools.check_exchanges` to run (ensures package imports resolve).
"""

from __future__ import annotations

import time
import traceback
from pathlib import Path
from typing import List

EXCHANGES = ["gateio", "binance", "kucoin", "bybit", "okx"]
TIMEOUT_MS = 30_000


def _write(lines: List[str]) -> None:
    p = Path("runtime") / "logs" / "exchanges_status.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def probe_exchange(ex_id: str) -> str:
    try:
        import ccxt  # type: ignore
    except Exception as e:
        return f"{ex_id}: SKIP (ccxt missing: {e})"

    # map alias to ccxt id if needed
    eid = ex_id
    try:
        ex_cls = getattr(ccxt, eid)
        ex = ex_cls({"enableRateLimit": True, "timeout": TIMEOUT_MS})
    except Exception:
        # try lowercase lookup
        try:
            ex_cls = getattr(ccxt, eid.lower())
            ex = ex_cls({"enableRateLimit": True, "timeout": TIMEOUT_MS})
        except Exception:
            return f"{ex_id}: FAILED to instantiate exchange client"

    # perform a light-weight probe: load_markets (may hit public endpoints)
    try:
        t0 = time.time()
        ex.load_markets()
        dt = time.time() - t0
        return f"{ex_id}: OK (load_markets {dt:.2f}s)"
    except Exception as e:
        return f"{ex_id}: ERROR {e}"


def main() -> int:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    lines: List[str] = [f"exchanges status {ts}"]
    for ex in EXCHANGES:
        try:
            res = probe_exchange(ex)
            lines.append(res)
        except Exception:
            lines.append(f"{ex}: probe crashed")
            lines.append(traceback.format_exc())

    ts2 = time.strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"done {ts2}")
    _write(lines)
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
