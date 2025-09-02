"""Simple market data fetcher using ccxt.

This module provides safe, opt-in helpers to fetch historical OHLCV and
persist to CSV under `runtime/data/`. It is intentionally conservative and
does not perform any live trading.
"""
from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


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

    # local retry loop
    ex_cls = getattr(ccxt, exchange_id, None)
    if ex_cls is None:
        raise RuntimeError(f"unknown exchange id: {exchange_id}")

    opts = {"enableRateLimit": True, "timeout": int(timeout_ms)}
    ex = ex_cls(opts)

    out: List[List[float]] = []
    attempt = 0
    while attempt < 3:
        try:
            params: Dict[str, Any] = {}
            if since is not None:
                params["since"] = since
            out = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit, params=params)  # type: ignore
            break
        except Exception as e:
            attempt += 1
            time.sleep(0.5 * attempt)
            if attempt >= 3:
                raise

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
