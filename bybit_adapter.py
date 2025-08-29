# bybit_adapter.py
from __future__ import annotations

import os, math, time
from typing import Dict, Any, Optional, List, Tuple
from dotenv import load_dotenv

try:
    import ccxt  # type: ignore
except Exception as e:  # pragma: no cover
    ccxt = None

load_dotenv()

# -------------------------------------------------
# Exchange init
# -------------------------------------------------
def bybit_init(
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    mode: str = "spot",
    enable_rate_limit: bool = True,
    timeout_ms: int = 20000,
):
    """
    Returns a ready ccxt.bybit instance for SPOT.
    Respects environment:
      EXCHANGE_ID (defaults to 'bybit')
      API_KEY, API_SECRET
      EXCHANGE_MODE (defaults to 'spot')
    """
    if ccxt is None:
        raise RuntimeError("ccxt is not installed (pip install ccxt)")

    ex_id = (os.getenv("EXCHANGE_ID") or "bybit").lower()
    if ex_id != "bybit":
        # still allow creating a Bybit instance even if EXCHANGE_ID is something else
        pass

    key = api_key or os.getenv("API_KEY") or ""
    sec = api_secret or os.getenv("API_SECRET") or ""

    default_type = (os.getenv("EXCHANGE_MODE") or mode or "spot").lower()

    from router import ExchangeRouter
    router = ExchangeRouter()
    # If you ever want testnet:
    # router.ex.set_sandbox_mode(True)
    return router


# -------------------------------------------------
# Market helpers
# -------------------------------------------------
def _load_markets(ex) -> Dict[str, Any]:
    if not getattr(ex, "markets", None):
        return ex.load_markets()
    return ex.markets

def map_symbol(symbol: str) -> str:
    """
    Normalize common variations (USD -> USDT for spot).
    """
    s = symbol.upper().replace("-", "/")
    if s.endswith("/USD"):
        s = s.replace("/USD", "/USDT")
    return s

def price_amount_precisions(ex, symbol: str) -> Tuple[int, int, float, float]:
    """
    Returns (price_precision_digits, amount_precision_digits,
             min_cost_notional, step_amount)
    """
    m = _load_markets(ex).get(symbol)
    if not m:
        raise RuntimeError(f"Unknown market {symbol!r} on {ex.id}")

    price_prec = int(m.get("precision", {}).get("price", 8))
    amt_prec   = int(m.get("precision", {}).get("amount", 8))

    limits     = m.get("limits", {}) or {}
    min_cost   = float(limits.get("cost", {}).get("min") or 0.0)  # min notional
    step_amt   = float(limits.get("amount", {}).get("step") or 0.0)

    # Bybit sometimes puts filters under info
    if min_cost <= 0:
        try:
            if "minNotional" in (m.get("info") or {}):
                min_cost = float(m["info"]["minNotional"])
        except Exception:
            pass

    return price_prec, amt_prec, min_cost, step_amt or 0.0

def floor_to_step(x: float, step: float, digits: int) -> float:
    if step and step > 0:
        n = math.floor(x / step) * step
    else:
        n = x
    # avoid zero because of tiny stake
    if n <= 0:
        return 0.0
    # round to precision digits
    return float(f"{n:.{digits}f}")


# -------------------------------------------------
# Data & balances
# -------------------------------------------------
def fetch_ohlcv(ex, symbol: str, timeframe: str = "1m", limit: int = 200) -> List[List[float]]:
    # Use router safe wrapper
    s = map_symbol(symbol)
    return ex.safe_fetch_ohlcv(s, timeframe=timeframe, limit=limit)

def account_summary_lines(ex, quote: str = "USDT") -> List[str]:
    try:
        bal = ex.safe_fetch_balance()
    except Exception as e:
        return [f"{ex.id} balance error: {e}"]

    lines: List[str] = []
    total = 0.0

    totals = (bal.get("total") or {})
    for asset, amt in sorted(totals.items()):
        try:
            v = float(amt or 0)
        except Exception:
            v = 0.0
        if v <= 0:
            continue
        est = 0.0
        try:
            if asset.upper() == quote.upper():
                est = v
            else:
                tkr = ex.safe_fetch_ticker(f"{asset}/{quote}")
                px = float(tkr.get("last") or tkr.get("close") or 0.0)
                if px > 0:
                    est = v * px
        except Exception:
            pass
        total += est
        lines.append(f"{asset:<6} {v:,.6f}  (~{total:,.2f} {quote})")

    if not lines:
        lines.append("(no balances or all zero)")
    lines.append(f"— estimated total: {total:,.2f} {quote}")
    return lines


# -------------------------------------------------
# Orders (SPOT, market)
# -------------------------------------------------
def ensure_can_trade(ex, symbol: str, side: str, usd_stake: float) -> Tuple[str, float]:
    """
    Validates and returns (ccxt_symbol, qty) for market order.
    Will raise RuntimeError with human message if stake is too small.
    """
    ccxt_sym = map_symbol(symbol)
    # Use router safe wrapper
    t = ex.safe_fetch_ticker(ccxt_sym)
    last = float(t.get("last") or t.get("close") or 0.0)
    if last <= 0:
        raise RuntimeError(f"Cannot resolve price for {ccxt_sym}")

    pr_digits, amt_digits, min_cost, step_amt = price_amount_precisions(ex, ccxt_sym)
    notional = float(max(min_cost, 0.0))
    qty_raw = usd_stake / last if last > 0 else 0.0
    qty = floor_to_step(qty_raw, step_amt, amt_digits)

    if qty <= 0:
        raise RuntimeError(f"Stake {usd_stake} too small for {ccxt_sym} (step={step_amt})")

    if notional > 0 and qty * last < notional:
        need = notional / last
        raise RuntimeError(f"Stake too small: need ≥ {notional} notional (~{need:.6f} units)")

    return ccxt_sym, qty

def order_market(
    ex,
    symbol: str,
    side: str,
    usd_stake: float,
    client_tag: str = "lt-spot",
) -> Dict[str, Any]:
    """
    Creates a market order on SPOT using USD-value stake.
    Returns {'ok': bool, 'id': str, 'symbol': str, 'side': str, 'amount': float, 'price': float, 'raw': ...}
    """
    side = side.lower().strip()
    if side not in ("buy", "sell"):
        raise RuntimeError("side should be 'buy' or 'sell'")

    ccxt_sym, qty = ensure_can_trade(ex, symbol, usd_stake)

    # create order using router safe wrapper
    try:
        o = ex.safe_place_order(ccxt_sym, side, qty)
        filled = float(o.get("filled") or 0.0)
        px     = float((o.get("average") or o.get("price") or 0.0))
        return {
            "ok": True,
            "id": str(o.get("id") or ""),
            "symbol": ccxt_sym,
            "side": side,
            "amount": filled or qty,
            "price": px,
            "raw": o,
        }
    except Exception as e:
        return {"ok": False, "error": f"Order error: {e}", "symbol": ccxt_sym}
