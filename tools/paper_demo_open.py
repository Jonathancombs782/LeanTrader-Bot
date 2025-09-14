"""Open several paper trades quickly for demo/testing.

Creates entries in runtime/open_trades.json using the project's ExchangeRouter
when `EXCHANGE_ID=paper` (safe). Quantities are computed from notional/last price.
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


def main():
    load_dotenv()
    from traders_core.router import ExchangeRouter

    RUNTIME = pathlib.Path("runtime")
    OPEN = RUNTIME / "open_trades.json"

    stake_usd = float(os.getenv("STAKE_USD", "5"))
    tp_pct = float(os.getenv("CRYPTO_TP_PCT", "0.002"))
    sl_pct = float(os.getenv("CRYPTO_SL_PCT", "0.001"))

    router = ExchangeRouter()
    syms = os.getenv("CRYPTO_SYMBOLS", "BTC/USDT,ETH/USDT").split(",")
    syms = [s.strip() for s in syms if s.strip()]

    rows: List[Dict[str, Any]] = _read(OPEN, [])

    for i, s in enumerate(syms[:5]):
        side = "buy" if i % 2 == 0 else "sell"
        px = router.last_price(s) or 0.0
        if px <= 0:
            # attempt to fetch a bar
            bars = router.fetch_ohlcv(s, "1m", limit=5)
            if bars:
                px = float(bars[-1][4])
        if px <= 0:
            print("skipping", s, "no price")
            continue
        qty = float(stake_usd) / float(px) if px else 0.0
        if qty <= 0:
            continue
        print(f"placing paper {side} {s} notional=${stake_usd} qty={qty:.6f}")
        res = router.place_spot_market(s, side, qty=qty)
        now = int(time.time())
        entry_price = px
        rec = {
            "symbol": s,
            "side": side,
            "mode": "spot",
            "amount": qty,
            "entry": entry_price,
            "tp_pct": tp_pct,
            "sl_pct": sl_pct,
            "leverage": 1,
            "opened_at": now,
            "result": res,
        }
        rows.append(rec)

    _write(OPEN, rows)
    print(f"wrote {len(rows)} open trades to {OPEN}")


if __name__ == "__main__":
    main()
