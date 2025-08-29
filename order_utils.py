"""order_utils.py - defensive helpers around order placement.

These helpers prefer router ExchangeRouter-style helpers when available (safe_place_order,
place_spot_market) and fall back to ccxt create_order with try/except. They return stable
dict shapes so callers can handle results uniformly.
"""

from __future__ import annotations
from typing import Any, Dict, Optional


def place_market(ex: Any, symbol: str, side: str, amount: float) -> Dict[str, Any]:
    """Place a market order, preferring safe helpers.

    Returns a dict or the raw exchange response if that's what the adapter returns.
    """
    side = side.lower()
    # Router-style helper
    try:
        if hasattr(ex, 'place_spot_market'):
            return ex.place_spot_market(symbol, side, qty=amount) if callable(getattr(ex, 'place_spot_market')) else ex.place_spot_market(symbol, side, amount)
        if hasattr(ex, 'safe_place_order'):
            return ex.safe_place_order(symbol, side, amount)
        if hasattr(ex, 'create_order'):
            try:
                # Use centralized safe_create_order to normalize adapter signatures
                return safe_create_order(ex, 'market', symbol, side, amount)
            except Exception as e:
                # Fall back to trying the adapter directly if safe_create_order fails
                try:
                    return ex.create_order(symbol, 'market', side, amount)
                except Exception:
                    try:
                        return ex.create_order(symbol, 'market', side, amount, None)
                    except Exception as e2:
                        return {"ok": False, "error": str(e2)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "no order method"}


def place_oco_ccxt(
    ex: Any,
    symbol: str,
    side: str,
    amount: float,
    entry_px: float,
    stop_px: Optional[float] = None,
    take_px: Optional[float] = None,
) -> Dict[str, Any]:
    """Best-effort OCO: market entry + optional TP/SL sibling orders.

    Returns a dict with keys: entry, tp, sl where values are the adapter responses or
    error dicts.
    """
    res: Dict[str, Any] = {"entry": None, "tp": None, "sl": None}

    # 1) entry
    res["entry"] = place_market(ex, symbol, side, amount)

    opp_side = "sell" if side.lower() == "buy" else "buy"

    # 2) TP
    if take_px is not None:
        try:
            if hasattr(ex, 'safe_place_order'):
                res["tp"] = ex.safe_place_order(symbol, opp_side, amount, price=take_px, params={})
            elif hasattr(ex, 'create_limit_order'):
                try:
                    res["tp"] = ex.create_limit_order(symbol, opp_side, amount, float(take_px))
                except Exception:
                    # fall back to centralized safe_create_order
                    try:
                        res["tp"] = safe_create_order(ex, 'limit', symbol, opp_side, amount, float(take_px))
                    except Exception:
                        res["tp"] = {"ok": False, "error": "tp create failed"}
            elif hasattr(ex, 'create_order'):
                try:
                    res["tp"] = safe_create_order(ex, 'limit', symbol, opp_side, amount, float(take_px), params={})
                except Exception:
                    try:
                        res["tp"] = safe_create_order(ex, 'limit', symbol, opp_side, amount, float(take_px))
                    except Exception:
                        res["tp"] = {"ok": False, "error": "tp create failed"}
            else:
                res["tp"] = {"ok": False, "error": "no tp order method"}
        except Exception as e:
            res["tp"] = {"ok": False, "error": str(e)}

    # 3) SL
    if stop_px is not None:
        try:
            params = {"stopPrice": float(stop_px)}
            if hasattr(ex, 'safe_place_order'):
                res["sl"] = ex.safe_place_order(symbol, opp_side, amount, price=None, params=params)
            elif hasattr(ex, 'create_stop_order'):
                try:
                    res["sl"] = ex.create_stop_order(symbol, opp_side, amount, float(stop_px), params=params)
                except Exception:
                    # fall back to centralized safe_create_order
                    try:
                        res["sl"] = safe_create_order(ex, 'stop', symbol, opp_side, amount, float(stop_px))
                    except Exception:
                        res["sl"] = {"ok": False, "error": "sl create failed"}
            elif hasattr(ex, 'create_order'):
                try:
                    res["sl"] = safe_create_order(ex, 'stop', symbol, opp_side, amount, None, params=params)
                except Exception:
                    try:
                        res["sl"] = safe_create_order(ex, 'stop', symbol, opp_side, amount, float(stop_px))
                    except Exception:
                        res["sl"] = {"ok": False, "error": "sl create failed"}
            else:
                res["sl"] = {"ok": False, "error": "no sl order method"}
        except Exception as e:
            res["sl"] = {"ok": False, "error": str(e)}

    return res


def safe_create_order(ex: Any, typ: str, symbol: str, side: str, amount: float, price: Optional[float] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Centralized, defensive create_order helper.
    Tries common adapter methods in a safe order and returns a stable dict or raw response.
    """
    # NOTE: This function is the canonical, centralized place to call into adapter
    # create_order methods; it normalizes adapter signatures, prefers router/adapter
    # safe helpers, and wraps direct adapter calls in guarded try/except blocks.
    try:
        typ = (typ or "").lower()
        # prefer router/adapter safe wrappers
        if hasattr(ex, 'safe_place_order'):
            return ex.safe_place_order(symbol, side, amount, price=price, params=params)

        # explicit market/limit/stop shims
        if typ == 'market':
            if hasattr(ex, 'create_market_order'):
                try:
                    return ex.create_market_order(symbol, side, amount)
                except Exception:
                    pass
            if hasattr(ex, 'create_order'):
                try:
                    return ex.create_order(symbol, 'market', side, amount)
                except Exception:
                    pass

        if typ == 'limit':
            if hasattr(ex, 'create_limit_order'):
                try:
                    return ex.create_limit_order(symbol, side, amount, price)
                except Exception:
                    pass
            if hasattr(ex, 'create_order'):
                try:
                    return ex.create_order(symbol, 'limit', side, amount, price, params or {})
                except Exception:
                    try:
                        return ex.create_order(symbol, 'limit', side, amount, price)
                    except Exception:
                        pass

        if typ in ('stop', 'stop_market', 'stop-limit'):
            if hasattr(ex, 'create_stop_order'):
                try:
                    return ex.create_stop_order(symbol, side, amount, price, params=params)
                except Exception:
                    pass
            if hasattr(ex, 'create_order'):
                try:
                    return ex.create_order(symbol, 'stop', side, amount, price, params or {})
                except Exception:
                    try:
                        return ex.create_order(symbol, 'stop', side, amount, price)
                    except Exception:
                        pass

        # last resort: try generic create_order if present
        if hasattr(ex, 'create_order'):
            try:
                return ex.create_order(symbol, typ or 'market', side, amount, price, params or {})
            except Exception:
                try:
                    return ex.create_order(symbol, typ or 'market', side, amount)
                except Exception as e:
                    # return normalized error dict instead of raising
                    return {"ok": False, "error": str(e)}

        # final safety: ensure we never raise from this public helper
        return {"ok": False, "error": "create_order not available or failed"}

        # fall back to place_market helper for safety
        return place_market(ex, symbol, side, amount)
    except Exception as e:
        return {"ok": False, "error": str(e)}
