# trade_planner.py
# Convert signals → executable plans; can place OCO on CCXT (Bybit/Binance best-effort).

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple  # noqa: F401  # intentionally kept

try:
    from risk_engine import Equity, plan_crypto, plan_fx
except Exception:
    # risk_engine may be unavailable in some test environments; provide light fallbacks
    Equity = float

    def plan_crypto(*a, **k):
        return {}

    def plan_fx(*a, **k):
        return {}


from order_utils import place_market
from session_filter import crypto_session_weight, fx_session_weight  # noqa: F401  # intentionally kept

EXCHANGE_MODE = os.getenv("EXCHANGE_MODE", "spot").lower()  # "spot" | "linear"

# Safety / sizing defaults
RISK_PCT_PER_TRADE = float(os.getenv("RISK_PCT_PER_TRADE", "1.0"))  # percent of equity risked per trade
MIN_NOTIONAL_USD = float(os.getenv("MIN_NOTIONAL_USD", "10"))
FUT_DEFAULT_LEVERAGE = int(os.getenv("FUT_DEFAULT_LEVERAGE", "3"))

# Awareness application flags
AW_APPLY_SIZING = os.getenv("AW_APPLY_SIZING", "true").strip().lower() in ("1", "true", "yes", "on")
AW_APPLY_LEVELS = os.getenv("AW_APPLY_LEVELS", "true").strip().lower() in ("1", "true", "yes", "on")


# ---------- merge helpers ----------
def _merge_weight(sig: Dict[str, Any], base_conf: float, sess_w: float) -> float:
    # confidence * session weight, clipped 0..1
    return max(0.0, min(1.0, base_conf * sess_w))


def attach_plan(sig: Dict[str, Any], equity: Any) -> Dict[str, Any]:
    """
    Given a signal dict {market, symbol, side, entry, sl, [atr], [tf] ...}
    return enriched dict with qty, tp ladder, leverage hints, and session tag.
    """
    s = dict(sig)  # copy
    s.get("market", "crypto").lower()
    side = s.get("side", "buy").lower()
    float(s.get("atr", 0.0) or 0.0)
    entry = float(s.get("entry", 0.0) or 0.0)
    sl = float(s.get("sl", 0.0) or 0.0)

    # Apply Awareness levels first (so we don't bail out due to missing SL)
    try:
        if AW_APPLY_LEVELS and entry > 0.0:
            aw_stop_atr = float(s.get("aw_stop_atr", 0.0) or 0.0)
            aw_take_atr = float(s.get("aw_take_atr", 0.0) or 0.0)
            side_ = (s.get("side") or "buy").lower()
            if aw_stop_atr > 0.0 and sl <= 0.0:
                sl = entry - aw_stop_atr if side_ == "buy" else entry + aw_stop_atr
                s["sl"] = sl
            # Populate TP ladder if not present
            if aw_take_atr > 0.0 and not all(k in s for k in ("tp1", "tp2", "tp3")):
                if side_ == "buy":
                    s["tp1"], s["tp2"], s["tp3"] = entry + aw_take_atr, entry + 2 * aw_take_atr, entry + 3 * aw_take_atr
                else:
                    s["tp1"], s["tp2"], s["tp3"] = entry - aw_take_atr, entry - 2 * aw_take_atr, entry - 3 * aw_take_atr
    except Exception:
        pass

    # Guard: if entry or sl missing/zero, mark plan as non-executable and avoid huge qty
    if entry <= 0.0 or sl <= 0.0:
        s["qty"] = 0.0
        # demote confidence so it won't be selected
        s["confidence"] = float(s.get("confidence", s.get("quality", 0.0)) or 0.0) * 0.0
        s.setdefault("context", []).append("missing_price_or_sl")
        # ensure TP/SL fields exist but are zero-safe
        s.setdefault("tp1", 0.0)
        s.setdefault("tp2", 0.0)
        s.setdefault("tp3", 0.0)
        s.setdefault("entry", entry)
        s.setdefault("sl", sl)
        return s

    # compute raw R (price distance). If invalid, fallback to small fraction
    R = abs(entry - sl) if (entry and sl and entry != sl) else max(0.001, abs(entry) * 0.003)

    # equity may be an object or numeric; try to get numeric total
    try:
        eq_val = float(getattr(equity, "total", equity) or equity)
    except Exception:
        try:
            eq_val = float(equity or 5000.0)
        except Exception:
            eq_val = 5000.0

    # compute risk per trade in USD
    risk_per_trade = (RISK_PCT_PER_TRADE / 100.0) * eq_val

    # naive qty estimate: if entry price in quote (e.g., USD), qty = risk_per_trade / R
    try:
        qty_by_risk = risk_per_trade / R if R > 0 else 0.0
    except Exception:
        qty_by_risk = 0.0

    # fallback notional-based qty
    try:
        qty_notional = MIN_NOTIONAL_USD / entry if entry > 0 else 0.0
    except Exception:
        qty_notional = 0.0

    raw_qty = max(qty_by_risk, qty_notional)

    # Apply Awareness sizing (fraction of equity → qty at entry)
    try:
        if AW_APPLY_SIZING and entry > 0.0:
            aw_frac = float(s.get("aw_size_frac", 0.0) or 0.0)
            if aw_frac > 0.0 and eq_val > 0.0:
                qty_aw = (eq_val * aw_frac) / entry
                if qty_aw > 0.0:
                    raw_qty = max(raw_qty, qty_aw)
    except Exception:
        pass

    # clamp raw_qty to a sane multiple of equity to avoid absurd sizes when R is tiny
    try:
        max_qty = max(1.0, eq_val * 10.0)
        if raw_qty > max_qty:
            raw_qty = max_qty
    except Exception:
        pass

    # clamp qty using exchange precision/step if router available on sig
    try:
        ex = None
        if "router" in s and hasattr(s["router"], "precision"):
            ex = s["router"]
        # if exchange provided as ExchangeRouter instance
        if ex is None:
            from router import ExchangeRouter  # noqa: F401  # intentionally kept

            # no router instance; leave raw_qty
        else:
            step = ex.precision(s.get("symbol"))
            try:
                # round down to nearest step
                raw_qty = float(int(raw_qty / step) * step) if step and step > 0 else raw_qty
            except Exception:
                pass
    except Exception:
        pass

    # leverage hint for futures
    lev = FUT_DEFAULT_LEVERAGE if EXCHANGE_MODE != "spot" else None

    s["qty"] = float(max(0.0, raw_qty))
    s["leverage"] = lev

    # populate tp ladder: default 1x,2x,3x multiples of R
    if not all(k in s for k in ("tp1", "tp2", "tp3")):
        if side == "buy":
            s["tp1"] = entry + 1.0 * R
            s["tp2"] = entry + 2.0 * R
            s["tp3"] = entry + 3.0 * R
        else:
            s["tp1"] = entry - 1.0 * R
            s["tp2"] = entry - 2.0 * R
            s["tp3"] = entry - 3.0 * R

    s["session"] = s.get("session", "auto")
    s["session_w"] = s.get("session_w", 1.0)
    base = float(s.get("confidence", s.get("quality", 0.0)) or 0.0)
    s["confidence"] = _merge_weight(s, base, s["session_w"])
    s.setdefault("context", []).append(f"risk_pct={RISK_PCT_PER_TRADE}% min_notional={MIN_NOTIONAL_USD}")
    return s


# ---------- CCXT OCO best-effort ----------
def place_oco_ccxt_safe(
    ex,
    symbol: str,
    side: str,
    qty: float,
    entry_px: float,
    stop_px: float,
    take_px: float,
    leverage: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Tries:
      1) single market/limit with 'takeProfit'/'stopLoss' params (e.g. Bybit)
      2) market entry + separate TP + SL orders
    Returns a dict of what succeeded.
    """
    out = {
        "entry": None,
        "tp": None,
        "sl": None,
        "mode": os.getenv("EXCHANGE_MODE", "spot"),
    }
    side = side.lower()

    params = {}
    # Exchange-specific hints
    try:
        x = getattr(ex, "ex", ex)  # unwrap router -> ccxt exchange if needed
        ex_id = getattr(x, "id", "").lower()
    except Exception:
        ex_id = ""
    # Common hints
    params["reduceOnly"] = True
    # Binance futures prefers GTC and may accept postOnly for TP
    if ex_id == "binance":
        params.setdefault("timeInForce", "GTC")
        params.setdefault("postOnly", True)
    # OKX may require postOnly for limit TP; let adapter map reduceOnly appropriately
    if ex_id == "okx":
        params.setdefault("postOnly", True)
    if leverage and hasattr(ex, "set_leverage"):
        try:
            ex.set_leverage(leverage, symbol)
        except Exception:
            pass

    # 1) unified params route
    try:
        params1 = dict(params)
        params1["takeProfit"] = float(take_px)
        params1["stopLoss"] = float(stop_px)
        # For binance/okx add explicit flags too
        if ex_id == "binance":
            params1.setdefault("timeInForce", "GTC")
        if ex_id == "okx":
            params1.setdefault("postOnly", True)
        # Prefer safe wrapper on adapters or router helpers
        if hasattr(ex, "safe_place_order"):
            out["entry"] = ex.safe_place_order(symbol, side, qty, params=params1)
            return out
        if hasattr(ex, "place_spot_market"):
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
        if hasattr(ex, "create_market_order"):
            try:
                out["entry"] = ex.create_market_order(symbol, side, qty)
            except Exception:
                pass
            if out.get("entry") is None:
                try:
                    from order_utils import safe_create_order

                    out["entry"] = safe_create_order(ex, "market", symbol, side, qty, price=None, params=params1)
                except Exception:
                    try:
                        from order_utils import safe_create_order

                        out["entry"] = safe_create_order(ex, "market", symbol, side, qty)
                    except Exception:
                        out["entry"] = {"ok": False, "error": "create_order failed"}
            return out
        out["entry"] = {"ok": False, "error": "no order method available"}
        return out
    except Exception:
        pass

    # 2) fallback: market + separate orders (exchange must support post-only TP/SL)
    try:
        if hasattr(ex, "safe_place_order"):
            out["entry"] = ex.safe_place_order(symbol, side, qty)
        elif hasattr(ex, "place_spot_market"):
            try:
                out["entry"] = ex.place_spot_market(symbol, side, qty=qty)
            except Exception:
                out["entry"] = {"ok": False, "error": "entry failed"}
        elif hasattr(ex, "create_order"):
            try:
                # prefer centralized safe_create_order wrapper
                out["entry"] = safe_create_order(ex, "market", symbol, side, qty)
            except Exception:
                out["entry"] = {"ok": False, "error": "entry failed"}
        else:
            out["entry"] = {"ok": False, "error": "no order method available"}
    except Exception as e:
        out["error"] = f"entry failed: {e}"
        return out

    try:
        # TP: opposite side
        tp_side = "sell" if side == "buy" else "buy"
        if hasattr(ex, "safe_place_order"):
            p_tp = dict(params)
            p_tp.setdefault("postOnly", True)
            out["tp"] = ex.safe_place_order(symbol, tp_side, qty, price=float(take_px), params=p_tp)
        elif hasattr(ex, "create_limit_order"):
            try:
                p_tp = dict(params)
                p_tp.setdefault("postOnly", True)
                out["tp"] = ex.create_limit_order(symbol, tp_side, qty, float(take_px))
            except Exception:
                try:
                    if hasattr(ex, "create_order"):
                        out["tp"] = safe_create_order(
                            ex,
                            "limit",
                            symbol,
                            tp_side,
                            qty,
                            float(take_px),
                            params=p_tp,
                        )
                    else:
                        out["tp"] = {"ok": False, "error": "tp create failed"}
                except Exception:
                    out["tp"] = {"ok": False, "error": "tp create failed"}
        elif hasattr(ex, "place_spot_market"):
            out["tp"] = ex.place_spot_market(symbol, tp_side, qty=qty)
        elif hasattr(ex, "create_order"):
            try:
                from order_utils import safe_create_order

                p_tp = dict(params)
                p_tp.setdefault("postOnly", True)
                out["tp"] = safe_create_order(ex, "limit", symbol, tp_side, qty, float(take_px), params=p_tp)
            except Exception:
                try:
                    from order_utils import safe_create_order

                    out["tp"] = safe_create_order(ex, "limit", symbol, tp_side, qty, float(take_px))
                except Exception:
                    out["tp"] = {"ok": False, "error": "tp create failed"}
        else:
            out["tp"] = {"ok": False, "error": "no order method available"}
    except Exception:
        out["tp"] = "tp_unsupported"

    try:
        # SL via stop-market if available
        sl_side = "sell" if side == "buy" else "buy"
        p = dict(params)
        # common param names across bybit/binance/okx
        p.update({"stopPrice": float(stop_px), "reduceOnly": True})
        if hasattr(ex, "safe_place_order"):
            out["sl"] = ex.safe_place_order(symbol, sl_side, qty, params=p)
        elif hasattr(ex, "create_stop_order"):
            try:
                out["sl"] = ex.create_stop_order(symbol, sl_side, qty, float(stop_px), params=p)
            except Exception:
                try:
                    if hasattr(ex, "create_order"):
                        out["sl"] = safe_create_order(ex, "stop", symbol, sl_side, qty, None, params=p)
                    else:
                        out["sl"] = {"ok": False, "error": "sl create failed"}
                except Exception:
                    out["sl"] = {"ok": False, "error": "sl create failed"}
        elif hasattr(ex, "place_spot_market"):
            out["sl"] = ex.place_spot_market(symbol, sl_side, qty=qty)
        elif hasattr(ex, "create_order"):
            try:
                from order_utils import safe_create_order

                out["sl"] = safe_create_order(ex, "stop", symbol, sl_side, qty, None, params=p)
            except Exception:
                try:
                    from order_utils import safe_create_order

                    out["sl"] = safe_create_order(ex, "stop", symbol, sl_side, qty, float(stop_px))
                except Exception:
                    out["sl"] = {"ok": False, "error": "sl create failed"}
        else:
            out["sl"] = {"ok": False, "error": "no order method available"}
    except Exception:
        out["sl"] = "sl_unsupported"

    return out
