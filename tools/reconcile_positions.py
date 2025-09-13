"""Reconcile runtime/open_trades.json with broker/account holdings.

Goals:
 - Query router account balances/positions
 - For each open trade, ensure the recorded amount matches available holdings
 - If mismatch, update runtime/open_trades.json to reflect canonical quantities
 - Emit a reconciliation log under runtime/reconcile_log.json
"""

from __future__ import annotations

import json
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


def reconcile():
    load_dotenv()
    from traders_core.router import ExchangeRouter

    RUNTIME = pathlib.Path("runtime")
    OPEN = RUNTIME / "open_trades.json"
    LOG = RUNTIME / "reconcile_log.json"

    rows: List[Dict[str, Any]] = _read(OPEN, [])
    if not rows:
        print("no open trades to reconcile")
        return

    router = ExchangeRouter()
    log: List[Dict[str, Any]] = _read(LOG, [])

    changed = 0
    for t in rows:
        sym = t.get("symbol")
        if not sym:
            continue
        recorded = float(t.get("amount", t.get("qty", 0)))
        available = _get_available_qty(router, sym)

        entry = {
            "ts": int(time.time()),
            "symbol": sym,
            "recorded": recorded,
            "available": available,
        }

        if available is None:
            entry["note"] = "no_account_info"
        elif abs(available - recorded) > max(1e-8, recorded * 0.005):
            # more than 0.5% mismatch -> adjust
            entry["note"] = "adjusted"
            entry["old_amount"] = recorded
            entry["new_amount"] = available
            t["amount"] = available
            changed += 1
        else:
            entry["note"] = "ok"

        log.append(entry)

    if changed > 0:
        _write(OPEN, rows)
    _write(LOG, log)
    print(f"reconcile done. changed={changed} entries logged={len(log)}")


if __name__ == "__main__":
    reconcile()
