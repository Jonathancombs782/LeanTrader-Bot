from __future__ import annotations

from typing import Any, Dict


def estimate_price_impact_from_book(orderbook: Dict[str, Any], qty: float) -> float:
    """Estimate price impact in basis points using linearized slope from top-of-book.

    Approximation: slope ~= (ask - bid) / ask_size, impact_bps ~= (slope * qty) / ask * 1e4.
    """
    try:
        bid = float(orderbook.get("bid", 0.0))
        ask = float(orderbook.get("ask", 0.0))
        ask_size = float(orderbook.get("ask_size", 0.0))
        if ask <= 0 or ask_size <= 0 or qty <= 0:
            return float("inf")
        spread = max(0.0, ask - bid)
        slope = spread / max(1e-12, ask_size)
        delta = slope * float(qty)
        bps = delta / max(1e-12, ask) * 1e4
        return float(max(0.0, bps))
    except Exception:
        return float("inf")


def max_safe_qty(orderbook: Dict[str, Any], bps_cap: float) -> float:
    """Maximum qty such that estimated impact <= bps_cap.

    Inverts the linearized formula: qty_max ~= (bps_cap/1e4) * ask / slope.
    """
    try:
        bid = float(orderbook.get("bid", 0.0))
        ask = float(orderbook.get("ask", 0.0))
        ask_size = float(orderbook.get("ask_size", 0.0))
        if ask <= 0 or ask_size <= 0:
            return 0.0
        spread = max(0.0, ask - bid)
        slope = spread / max(1e-12, ask_size)
        if slope <= 1e-12:
            return float("inf")
        qty = (float(bps_cap) / 1e4) * ask / slope
        return float(max(0.0, qty))
    except Exception:
        return 0.0


def _fetch_orderbook(venue: str, symbol: str) -> Dict[str, Any]:
    try:
        from traders_core.connectors.crypto_ccxt import _mk_exchange as mk_ex  # type: ignore

        ex = mk_ex(venue, False)
        ob = ex.fetch_order_book(symbol, limit=5)
        bids = ob.get("bids") or []
        asks = ob.get("asks") or []
        return {
            "bid": float(bids[0][0]) if bids else 0.0,
            "bid_size": float(bids[0][1]) if bids else 0.0,
            "ask": float(asks[0][0]) if asks else 0.0,
            "ask_size": float(asks[0][1]) if asks else 0.0,
        }
    except Exception:
        return {"bid": 0.0, "bid_size": 0.0, "ask": 0.0, "ask_size": 0.0}


def guard_order(symbol: str, venue: str, qty: float, bps_cap: float = 30.0) -> float:
    """Return a possibly reduced qty that respects the impact cap.

    Fetches a small orderbook snapshot and computes max safe qty.
    """
    ob = _fetch_orderbook(venue, symbol)
    qmax = max_safe_qty(ob, float(bps_cap))
    return float(min(float(qty), qmax))


__all__ = ["estimate_price_impact_from_book", "max_safe_qty", "guard_order"]

