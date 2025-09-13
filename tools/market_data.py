"""Simple market data fetcher using ccxt.

This module provides safe, opt-in helpers to fetch historical OHLCV and
persist to CSV under `runtime/data/`. It is intentionally conservative and
does not perform any live trading.
"""

from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# A small mapping of common friendly names to ccxt exchange ids. Users can
# pass either the key or the ccxt id. This keeps things flexible and "universal".
EXCHANGE_ALIASES = {
    "binance": "binance",
    "bybit": "bybit",
    "gateio": "gateio",
    "kucoin": "kucoin",
    "coinbase": "coinbasepro",
    "coinbasepro": "coinbasepro",
    "okx": "okx",
    "okex": "okx",
}


def _ensure_runtime_dir() -> Path:
    p = Path("runtime") / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def fetch_ohlcv(
    exchange_id: str,
    symbol: str,
    timeframe: str = "1m",
    since: Optional[int] = None,
    limit: int = 1000,
    timeout_ms: int = 30_000,
) -> List[List[float]]:
    """Fetch OHLCV via ccxt. Returns list of rows [ts, o, h, l, c, v].

    This function requires `ccxt` to be installed. It is safe to call in a
    non-live environment; it only reads market data.
    """
    try:
        import ccxt  # type: ignore
    except Exception as e:
        raise RuntimeError("ccxt is required for market data fetching") from e

    # resolve alias
    exch_key = EXCHANGE_ALIASES.get(exchange_id.lower(), exchange_id.lower())

    ex_cls = getattr(ccxt, exch_key, None)
    if ex_cls is None:
        # some environments expose ccxt.exchange classes under different names
        # fall back to ccxt.Exchange and instantiate by id using ccxt's factory
        try:
            ex = ccxt.__dict__.get(exch_key)
        except Exception:
            ex = None
        if ex is None:
            raise RuntimeError(f"unknown exchange id or alias: {exchange_id}")
    else:
        opts = {"enableRateLimit": True, "timeout": int(timeout_ms)}
        ex = ex_cls(opts)

    # Try several common symbol variants to increase compatibility across
    # exchanges (some use different separators or market ids).
    def _symbol_variants(s: str) -> List[str]:
        s = s.strip()
        variants = [s]
        if "/" in s:
            base, quote = s.split("/", 1)
            variants.extend(
                [
                    f"{base}{quote}",  # BTCUSDT
                    f"{base}-{quote}",  # BTC-USDT
                    f"{base}_{quote}",  # BTC_USDT
                    f"{base}/{quote}:USDT" if quote.upper() == "USDT" else f"{base}/{quote}",
                ]
            )
        else:
            # if user passed BTCUSDT, try BTC/USDT
            if len(s) >= 6:
                variants.append(s[:3] + "/" + s[3:])
        # de-duplicate while preserving order
        out_vars: List[str] = []
        for v in variants:
            if v not in out_vars:
                out_vars.append(v)
        return out_vars

    params: Dict[str, Any] = {}
    if since is not None:
        params["since"] = since

    out: List[List[float]] = []
    attempt = 0
    last_exc: Optional[Exception] = None
    for attempt in range(1, 4):
        for try_sym in _symbol_variants(symbol):
            try:
                out = ex.fetch_ohlcv(try_sym, timeframe=timeframe, limit=limit, params=params)  # type: ignore
                # on success, persist using the original safe_sym naming
                attempt = 0
                last_exc = None
                break
            except Exception as e:
                last_exc = e
                # try next variant
                time.sleep(0.1)
                continue
        if out:
            break
        # small backoff before full retry cycle
        time.sleep(0.5 * attempt)
    if not out and last_exc is not None:
        raise last_exc

    # persist to CSV for later use
    runtime = _ensure_runtime_dir()
    safe_sym = symbol.replace("/", "_")
    fname = runtime / f"{exchange_id}_{safe_sym}_{timeframe}.csv"
    try:
        with fname.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["ts", "open", "high", "low", "close", "vol"])
            for row in out:
                writer.writerow(row)
    except Exception:
        # ignore persistence errors
        pass
    return out


def fetch_ohlcv_multi(
    exchange_ids: List[str],
    symbol: str,
    timeframe: str = "1m",
    since: Optional[int] = None,
    limit: int = 1000,
    timeout_ms: int = 30_000,
) -> Tuple[str, List[List[float]]]:
    """Try multiple exchanges in order, return (exchange_used, rows).

    Useful when you want a universal fallback across exchanges that list the
    same market under slightly different ids.
    """
    last_exc: Optional[Exception] = None
    for ex in exchange_ids:
        try:
            rows = fetch_ohlcv(ex, symbol, timeframe=timeframe, since=since, limit=limit, timeout_ms=timeout_ms)
            return ex, rows
        except Exception as e:
            last_exc = e
            continue
    # if none succeeded, raise the last exception
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("no exchanges provided")


def load_csv(exchange_id: str, symbol: str, timeframe: str = "1m") -> List[List[float]]:
    runtime = Path("runtime") / "data"
    safe_sym = symbol.replace("/", "_")
    fname = runtime / f"{exchange_id}_{safe_sym}_{timeframe}.csv"
    if not fname.exists():
        return []
    out: List[List[float]] = []
    with fname.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            try:
                out.append([int(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])])
            except Exception:
                continue
    return out
