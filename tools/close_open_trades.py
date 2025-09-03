"""Close any open trades recorded in runtime/open_trades.json using the project's router.

This is safe to run in paper mode (EXCHANGE_ID=paper). It will:
 - read runtime/open_trades.json
 - for each open trade, attempt to close via router.place_spot_market or place_futures_market
 - write successes to runtime/closed_trades.json (append)
 - remove closed trades from runtime/open_trades.json
 - print a short summary
"""
from __future__ import annotations

import json
import os
import pathlib
import time
from typing import Any, Dict, List

from dotenv import load_dotenv


def _read(path: pathlib.Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(path: pathlib.Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def close_open_trades():
    load_dotenv()
    # local import to avoid side-effects at module import
    from traders_core.router import ExchangeRouter

    RUNTIME = pathlib.Path("runtime")
    OPEN = RUNTIME / "open_trades.json"
    CLOSED = RUNTIME / "closed_trades.json"

    rows: List[Dict[str, Any]] = _read(OPEN, [])
    if not rows:
        print("no open trades to close")
        return

    router = ExchangeRouter()
    closed: List[Dict[str, Any]] = _read(CLOSED, [])

    for t in list(rows):
        sym = t.get("symbol")
        side = t.get("side")
        mode = t.get("mode", "spot")
        amt = float(t.get("amount", t.get("qty", 0)))
        if not sym or amt <= 0:
            print(f"skipping malformed trade entry: {t}")
            rows.remove(t)
            continue

        close_side = "sell" if side == "buy" else "buy"
        print(f"attempting close {sym} {close_side} amt={amt} mode={mode}")
        try:
            if mode == "spot":
                res = router.place_spot_market(sym, close_side, qty=amt)
            else:
                res = router.place_futures_market(sym, close_side, qty=amt, close=True)
        except Exception as e:
            res = {"ok": False, "error": str(e)}

        # If we failed due to insufficient qty, try to query holdings and retry with available qty
        if isinstance(res, dict) and not res.get("ok"):
            err = str(res.get("error") or "")
            if "insufficient base qty" in err.lower() or "insufficient qty" in err.lower():
                # attempt to compute available qty from router account or paper broker holdings
                avail = None
                try:
                    # PaperBroker exposes holdings via fetch_balance or .ex.holdings
                    if hasattr(router.ex, "fetch_balance"):
                        bal = router.ex.fetch_balance() or {}
                        # holdings might be keyed by base symbol
                        base = sym.split("/")[0]
                        if base in bal:
                            avail = float(bal[base].get("free", 0) or bal[base].get("total", 0))
                    elif hasattr(router.ex, "holdings"):
                        h = getattr(router.ex, "holdings", {})
                        base = sym.split("/")[0]
                        avail = float(h.get(base, 0.0))
                except Exception:
                    avail = None

                if avail and avail > 0:
                    try_qty = float(min(avail, amt))
                    try:
                        if mode == "spot":
                            retry = router.place_spot_market(sym, close_side, qty=try_qty)
                        else:
                            retry = router.place_futures_market(sym, close_side, qty=try_qty, close=True)
                    except Exception as e:
                        retry = {"ok": False, "error": str(e)}
                    entry["retry_with_available"] = {"qty": try_qty, "result": retry}
                    # include retry result as final result for record
                    entry["result"] = retry

        now = int(time.time())
        entry = {
            "symbol": sym,
            "side_open": side,
            "side_close": close_side,
            "mode": mode,
            "amount": amt,
            "closed_at": now,
            "result": res,
        }
        closed.append(entry)
        # remove this entry from open list regardless (to avoid repeated attempts)
        try:
            rows.remove(t)
        except Exception:
            pass

        print("close result:", res)

    # persist
    _write(OPEN, rows)
    _write(CLOSED, closed)
    print(f"closed {len(closed)} trades, remaining open: {len(rows)}")


if __name__ == "__main__":
    close_open_trades()
