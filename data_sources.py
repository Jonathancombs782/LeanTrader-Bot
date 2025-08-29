# data_sources.py
from __future__ import annotations

import os, time, math, random
from typing import List, Dict, Optional, Any, Tuple

# ccxt is optional in FX-only setups
try:
    import ccxt  # type: ignore
except Exception:  # pragma: no cover
    ccxt = None

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

# ---------------------------------------------------------------------
# Exchange fallbacks: try primary first, then these in order if it 403's,
# needs apiKey, or otherwise fails.  Gate.io included.
# Keys are ccxt ids.
EX_ROUTES: Dict[str, List[str]] = {
    "binanceus": ["gateio", "kraken", "okx", "kucoin"],
    "binance":   ["kraken", "okx", "kucoin", "gateio"],
    "bybit":     ["gateio", "okx", "kucoin", "kraken"],
    "kraken":    ["okx", "gateio", "binance"],
    "okx":       ["kraken", "gateio", "binance"],
    "kucoin":    ["gateio", "okx", "kraken"],
    "gateio":    ["kraken", "okx", "kucoin", "binance"],
}

def _has_ccxt() -> bool:
    return ccxt is not None

def _build_ex(ex_id: str):
    """
    Build a ccxt exchange with safe defaults for public market data.
    Uses env keys if present; otherwise public-only works for most venues.
    """
    if not _has_ccxt():
        raise RuntimeError("ccxt not installed")

    klass = getattr(ccxt, ex_id)
    cfg = {
        "enableRateLimit": True,
        "timeout": 15000,
        "headers": {"User-Agent": USER_AGENT},
    }
    # If user provided keys for this venue, attach them
    env_key  = os.getenv("API_KEY") or ""
    env_sec  = os.getenv("API_SECRET") or ""
    env_id   = (os.getenv("EXCHANGE_ID") or "").lower().strip()
    if env_id == ex_id and env_key and env_sec:
        cfg["apiKey"] = env_key
        cfg["secret"] = env_sec
    return klass(cfg)

def _map_symbol_for(ex_id: str, symbol: str) -> str:
    """
    Map 'BASE/USD' -> 'BASE/USDT' for venues that mainly quote in USDT.
    We *accept* USD input in your loops but translate to USDT where needed.
    """
    try:
        base, quote = symbol.split("/")
    except Exception:
        return symbol

    quote = quote.upper()
    # Most crypto venues want USDT
    if ex_id in ("binanceus", "binance", "bybit", "okx", "kucoin", "gateio") and quote == "USD":
        return f"{base}/USDT"
    return symbol

def _is_geo_or_cred_error(e: Exception) -> bool:
    s = str(e).lower()
    # common patterns: 403 forbidden cloudfront, requires apikey, not available in your country, etc.
    return any(k in s for k in [
        "403", "forbidden", "cloudfront", "your country", "requires \"apikey\"", "requires 'apikey'",
        "permission", "denied", "not available in your country"
    ])

def fetch_ohlcv_router(ex_primary, symbol: str, timeframe: str, limit: int = 400,
                       since: Optional[int] = None,
                       backups: Optional[List[str]] = None) -> List[List[Any]]:
    """
    Try primary ccxt exchange first.  If it fails with geo/API-key issues,
    automatically fall back through EX_ROUTES (including Gate.io).
    Returns a standard ccxt OHLCV array: [ts, o, h, l, c, v] rows.
    """
    if not _has_ccxt():
        raise RuntimeError("ccxt not installed")

    tried: List[str] = []
    primary_id = getattr(ex_primary, "id", "").lower()
    routes = list(backups or EX_ROUTES.get(primary_id, []))

    # small shuffle after first two to spread load
    if len(routes) > 2:
        head, tail = routes[:2], routes[2:]
        random.shuffle(tail)
        routes = head + tail

    # Attempt 1: primary
    try:
        s = _map_symbol_for(primary_id, symbol)
        # If caller passed an ExchangeRouter-like object, prefer its safe wrapper
        if hasattr(ex_primary, 'safe_fetch_ohlcv'):
            try:
                rows = ex_primary.safe_fetch_ohlcv(s, timeframe=timeframe, limit=limit, since=since)  # type: ignore[arg-type]
                if rows:
                    return rows
            except Exception as e:
                print(f"[data_sources] safe_fetch_ohlcv primary failed: {e}")
                # fall through to try direct fetch
        try:
            rows = ex_primary.fetch_ohlcv(s, timeframe=timeframe, limit=limit, since=since)
            if rows:
                return rows
            tried.append(primary_id)
        except Exception as e:
            tried.append(primary_id)
            # Log the error and continue to fallback routes; do not re-raise to avoid crashing callers
            print(f"[data_sources] primary fetch_ohlcv failed for {primary_id}: {e}")
    except Exception as e:
        tried.append(primary_id)
        if not _is_geo_or_cred_error(e):
            # Different error -> surface it
            raise

    # Fallbacks
    last_err = None
    for ex_id in routes:
        try:
            ex = _build_ex(ex_id)
            s = _map_symbol_for(ex_id, symbol)
            rows = ex.fetch_ohlcv(s, timeframe=timeframe, limit=limit, since=since)
            if rows:
                return rows
        except Exception as e:  # pragma: no cover
            last_err = e
            tried.append(ex_id)
            continue
    # If we reach here no route returned data; return empty list rather than raise so callers can handle gracefully
    print(f"[data_sources] fetch_ohlcv_router no data for {symbol}@{timeframe}; tried={tried}; last_err={last_err}")
    return []
