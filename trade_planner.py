# trade_planner.py
# Convert signals → executable plans; can place OCO on CCXT (Bybit/Binance best-effort).

from __future__ import annotations
import os
from typing import Dict, Any, Optional, Tuple

from risk_engine import Equity, plan_crypto, plan_fx
from session_filter import crypto_session_weight, fx_session_weight
from order_utils import place_market, safe_create_order

EXCHANGE_MODE = os.getenv("EXCHANGE_MODE", "spot").lower()   # "spot" | "linear"

# ---------- merge helpers ----------
def _merge_weight(sig: Dict[str, Any], base_conf: float, sess_w: float) -> float:
    # confidence * session weight, clipped 0..1
    return max(0.0, min(1.0, base_conf * sess_w))

def attach_plan(sig: Dict[str, Any], equity: Equity) -> Dict[str, Any]:
    """
    Given a signal dict {market, symbol, side, entry, sl, [atr], [tf] ...}
    return enriched dict with qty, tp ladder, leverage hints, and session tag.
    """
    s = dict(sig)  # copy
    mkt = s.get("market","crypto").lower()
    side = s.get("side","buy").lower()
    atr  = float(s.get("atr", 0.0) or 0.0)
    entry = float(s["entry"]); sl = float(s["sl"])

    if mkt.startswith("fx"):
        sess, w = fx_session_weight(s["symbol"])
        plan = plan_fx(entry, sl, side, equity, symbol=s["symbol"], atr=atr)
    else:
        sess, w = crypto_session_weight(s["symbol"])
        lev = int(os.getenv("FUT_DEFAULT_LEVERAGE","3")) if EXCHANGE_MODE!="spot" else None
        plan = plan_crypto(entry, sl, side, equity, leverage=lev, atr=atr)

    s["qty"] = plan.qty
    s["tp1"], s["tp2"], s["tp3"] = plan.tp1, plan.tp2, plan.tp3
    s["leverage"] = plan.leverage
    s["session"] = sess
    s["session_w"] = w
    base = float(s.get("confidence", s.get("quality", 0.0)) or 0.0)
    s["confidence"] = _merge_weight(s, base, w)
    s.setdefault("context", []).append(f"Session={sess} (w×{w:.2f})")
    if plan.warnings:
        s["context"].extend([f"⚠ {x}" for x in plan.warnings])
    return s

# ---------- CCXT OCO best-effort ----------
def place_oco_ccxt_safe(ex, symbol: str, side: str, qty: float, entry_px: float,
                        stop_px: float, take_px: float, leverage: Optional[int]=None) -> Dict[str,Any]:
    """
    Tries:
      1) single market/limit with 'takeProfit'/'stopLoss' params (e.g. Bybit)
      2) market entry + separate TP + SL orders
    Returns a dict of what succeeded.
    """
    out = {"entry": None, "tp": None, "sl": None, "mode": os.getenv("EXCHANGE_MODE","spot")}
    side = side.lower()

    params = {}
    if leverage and hasattr(ex, "set_leverage"):
        try: ex.set_leverage(leverage, symbol)
        except: pass

    # 1) unified params route
    try:
        params1 = dict(params)
        params1["takeProfit"] = float(take_px)
        params1["stopLoss"]   = float(stop_px)
        # Prefer safe wrapper on adapters or router helpers
        if hasattr(ex, 'safe_place_order'):
            out["entry"] = ex.safe_place_order(symbol, side, qty, params=params1)
            return out
        if hasattr(ex, 'place_spot_market'):
            try:
                res = ex.place_spot_market(symbol, side, qty=qty)
                out["entry"] = res.get("result") if isinstance(res, dict) else res
                return out
            except Exception:
                pass
        # fallback to normalized helper
        try:
            out["entry"] = place_market(ex, symbol, side, qty)
            return out
        except Exception:
            pass
        # final fallback: try create_order if present
        if hasattr(ex, 'create_market_order'):
            try:
                out["entry"] = ex.create_market_order(symbol, side, qty)
            except Exception:
                pass
        if out.get("entry") is None:
            try:
                from order_utils import safe_create_order
                out["entry"] = safe_create_order(ex, 'market', symbol, side, qty, price=None, params=params1)
            except Exception:
                try:
                    from order_utils import safe_create_order
                    out["entry"] = safe_create_order(ex, 'market', symbol, side, qty)
                except Exception:
                    out["entry"] = {"ok": False, "error": "create_order failed"}
            return out
        out["entry"] = {"ok": False, "error": "no order method available"}
        return out
    except Exception:
        pass

    # 2) fallback: market + separate orders (exchange must support post-only TP/SL)
    try:
        if hasattr(ex, 'safe_place_order'):
            out["entry"] = ex.safe_place_order(symbol, side, qty)
        elif hasattr(ex, 'place_spot_market'):
            try:
                out["entry"] = ex.place_spot_market(symbol, side, qty=qty)
            except Exception:
                out["entry"] = {"ok": False, "error": "entry failed"}
        elif hasattr(ex, 'create_order'):
            try:
                # prefer centralized safe_create_order wrapper
                out["entry"] = safe_create_order(ex, 'market', symbol, side, qty)
            except Exception:
                out["entry"] = {"ok": False, "error": "entry failed"}
        else:
            out["entry"] = {"ok": False, "error": "no order method available"}
    except Exception as e:
        out["error"] = f"entry failed: {e}"
        return out

    try:
        # TP: opposite side
        tp_side = "sell" if side=="buy" else "buy"
        if hasattr(ex, 'safe_place_order'):
            out["tp"] = ex.safe_place_order(symbol, tp_side, qty, price=float(take_px), params=params)
        elif hasattr(ex, 'create_limit_order'):
            try:
                out["tp"] = ex.create_limit_order(symbol, tp_side, qty, float(take_px))
            except Exception:
                try:
                    if hasattr(ex, 'create_order'):
                        out["tp"] = safe_create_order(ex, 'limit', symbol, tp_side, qty, float(take_px), params=params)
                    else:
                        out["tp"] = {"ok": False, "error": "tp create failed"}
                except Exception:
                    out["tp"] = {"ok": False, "error": "tp create failed"}
        elif hasattr(ex, 'place_spot_market'):
            out["tp"] = ex.place_spot_market(symbol, tp_side, qty=qty)
        elif hasattr(ex, 'create_order'):
            try:
                from order_utils import safe_create_order
                out["tp"] = safe_create_order(ex, 'limit', symbol, tp_side, qty, float(take_px), params=params)
            except Exception:
                try:
                    from order_utils import safe_create_order
                    out["tp"] = safe_create_order(ex, 'limit', symbol, tp_side, qty, float(take_px))
                except Exception:
                    out["tp"] = {"ok": False, "error": "tp create failed"}
        else:
            out["tp"] = {"ok": False, "error": "no order method available"}
    except Exception:
        out["tp"] = "tp_unsupported"

    try:
        # SL via stop-market if available
        sl_side = "sell" if side=="buy" else "buy"
        p = dict(params)
        # common param names across bybit/binance/okx
        p.update({"stopPrice": float(stop_px), "reduceOnly": True})
        if hasattr(ex, 'safe_place_order'):
            out["sl"] = ex.safe_place_order(symbol, sl_side, qty, params=p)
        elif hasattr(ex, 'create_stop_order'):
            try:
                out["sl"] = ex.create_stop_order(symbol, sl_side, qty, float(stop_px), params=p)
            except Exception:
                try:
                    if hasattr(ex, 'create_order'):
                        out["sl"] = safe_create_order(ex, 'stop', symbol, sl_side, qty, None, params=p)
                    else:
                        out["sl"] = {"ok": False, "error": "sl create failed"}
                except Exception:
                    out["sl"] = {"ok": False, "error": "sl create failed"}
        elif hasattr(ex, 'place_spot_market'):
            out["sl"] = ex.place_spot_market(symbol, sl_side, qty=qty)
        elif hasattr(ex, 'create_order'):
            try:
                from order_utils import safe_create_order
                out["sl"] = safe_create_order(ex, 'stop', symbol, sl_side, qty, None, params=p)
            except Exception:
                try:
                    from order_utils import safe_create_order
                    out["sl"] = safe_create_order(ex, 'stop', symbol, sl_side, qty, float(stop_px))
                except Exception:
                    out["sl"] = {"ok": False, "error": "sl create failed"}
        else:
            out["sl"] = {"ok": False, "error": "no order method available"}
    except Exception:
        out["sl"] = "sl_unsupported"

    return out
