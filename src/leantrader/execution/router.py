from __future__ import annotations

import os
from typing import Any, Dict

from .broker_ccxt import BrokerCCXT
from .broker_emulator import BrokerEmulator
from .broker_fx import BrokerFX


def route_order(payload: Dict[str, Any], mode: str = None) -> Dict[str, Any]:
    """Route an order dict to the selected backend.

    Payload expected keys: symbol, side, qty, price (optional for market), clientOrderId (optional)
    """
    m = (mode or os.getenv("BROKER_MODE", "emu")).lower()
    symbol = payload.get("symbol") or payload.get("pair")
    side = str(payload.get("side", "buy")).lower()
    qty = float(payload.get("qty", 0.0) or payload.get("quantity", 0.0) or 0.0)
    price = float(payload.get("price", 0.0))

    if m == "emu":
        emu = BrokerEmulator()
        return emu.market(symbol, side, qty, price)
    if m == "fx":
        return BrokerFX().market(symbol, side, qty, price)
    if m == "ccxt":
        return BrokerCCXT().market(symbol, side, qty, price)
    return {"ok": False, "error": f"Unknown broker mode: {m}"}
