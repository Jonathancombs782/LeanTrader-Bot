# crypto_cctx.py
from __future__ import annotations

import os
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

try:
    import ccxt  # type: ignore
except Exception:
    ccxt = None

import time
import pandas as pd

load_dotenv()


def make_exchange(ex_id: Optional[str] = None):
    if ccxt is None:
        raise RuntimeError("ccxt not installed: pip install ccxt")

    from router import ExchangeRouter
    router = ExchangeRouter()
    return router


def map_symbol(ex_id: str, symbol: str) -> str:
    """
    Normalize common '*/USD' to '*/USDT' for venues that quote in USDT.
    """
    base, sep, quote = symbol.replace("-", "/").upper().partition("/")
    if not sep:
        return symbol.upper()

    if ex_id in ("bybit", "gateio", "binance", "binanceus", "okx", "kucoin"):
        if quote == "USD":
            return f"{base}/USDT"
    return f"{base}/{quote}"


def fetch_ohlcv_df(ex, symbol: str, timeframe: str = "1m", limit: int = 200) -> pd.DataFrame:
    sym = map_symbol(ex.id, symbol)
    rows = ex.safe_fetch_ohlcv(sym, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(rows, columns=["time","open","high","low","close","volume"])
    if not df.empty:
        df["time"] = pd.to_datetime(df["time"], unit="ms")
    return df


def balance_lines(ex) -> List[str]:
    try:
        bal = ex.safe_fetch_balance()
    except Exception as e:
        return [f"{ex.id} balance error: {e}"]

    totals = (bal or {}).get("total") or {}
    lines: List[str] = []
    total_usd = 0.0
    for asset, amt in sorted(totals.items()):
        try:
            v = float(amt or 0)
        except Exception:
            v = 0.0
        if v <= 0:
            continue

        usd = v
        if asset.upper() not in ("USD", "USDT"):
            try:
                t = ex.safe_fetch_ticker(f"{asset}/USDT")
                px = float(t.get("last") or t.get("close") or 0)
                usd = v * px
            except Exception:
                pass
        total_usd += usd
        lines.append(f"{asset:<6} {v:,.6f}")
    lines.append(f"— est. total: ${total_usd:,.2f}")
    if not lines:
        lines = ["(no balances or all zero)"]
    return lines


def market_order_spot(ex, symbol: str, side: str, qty: float) -> Dict[str, Any]:
    """
    Place a SPOT market order for base-qty (e.g., BUY 25 DOGE).
    """
    sym = map_symbol(ex.id, symbol)
    side = side.lower().strip()
    if side not in ("buy", "sell"):
        raise ValueError("side must be 'buy' or 'sell'")
    try:
        order = ex.safe_place_order(sym, side, qty)
        return {"ok": True, "order": order}
    except Exception as e:
        return {"ok": False, "error": str(e)}
