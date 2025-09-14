"""Retry failed closes that failed with 'insufficient base qty'.

This will:
 - read runtime/closed_trades.json
 - for entries with insufficient-base errors, query available qty from router/ex
 - if available>0, place a market close for available qty and append retry result
"""

from __future__ import annotations

import json
import pathlib
import time

from dotenv import load_dotenv


def _read(path: pathlib.Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(path: pathlib.Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _get_available_qty(router, symbol: str):
    base = symbol.split("/")[0]
    ex = getattr(router, "ex", None)
    try:
        if ex is None:
            return None
        if hasattr(ex, "fetch_balance"):
            bal = ex.fetch_balance() or {}
            if isinstance(bal, dict):
                if base in bal and isinstance(bal[base], dict):
                    acct = bal.get(base) or {}
                    return float(acct.get("free", acct.get("total", 0)) or 0.0)
                if "total" in bal and isinstance(bal["total"], dict) and base in bal["total"]:
                    acct = bal["total"][base]
                    if isinstance(acct, dict):
                        return float(acct.get("free", acct.get("total", 0)) or 0.0)
        if hasattr(ex, "holdings"):
            h = getattr(ex, "holdings", {}) or {}
            if base in h:
                return float(h.get(base, 0.0) or 0.0)
    except Exception:
        return None
    return None


def main():
    load_dotenv()
    from traders_core.router import ExchangeRouter

    RUNTIME = pathlib.Path("runtime")
    CLOSED = RUNTIME / "closed_trades.json"

    closed = _read(CLOSED, [])
    if not closed:
        print("no closed trades to inspect")
        return

    router = ExchangeRouter()
    retried = 0

    for e in list(closed):
        # check top-level error or nested result
        res = e.get("result") or {}
        err = ""
        if isinstance(res, dict) and not res.get("ok"):
            err = str(res.get("error") or "")
        elif (
            isinstance(res, dict)
            and res.get("result")
            and isinstance(res.get("result"), dict)
            and not res.get("result").get("ok", True)
        ):
            err = str(res.get("result").get("error") or "")
        if "insufficient" not in err.lower():
            continue

        sym = e.get("symbol")
        if not sym:
            continue
        side_open = e.get("side_open")
        close_side = "sell" if side_open == "buy" else "buy"
        avail = _get_available_qty(router, sym)
        print(f"Retrying {sym}: available={avail}")
        if not avail or avail <= 0:
            continue

        # attempt a partial close with available qty
        try:
            res_retry = router.place_spot_market(sym, close_side, qty=avail)
        except Exception as ex:
            res_retry = {"ok": False, "error": str(ex)}

        entry = {
            "ts": int(time.time()),
            "symbol": sym,
            "retry_qty": float(avail),
            "retry_result": res_retry,
            "orig_index": None,
        }
        closed.append({"retried": True, **entry})
        retried += 1

    if retried:
        _write(CLOSED, closed)
    print(f"retry_failed_closes: retried={retried}")


if __name__ == "__main__":
    main()
