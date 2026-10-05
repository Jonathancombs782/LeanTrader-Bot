"""Daily OHLC history feeds for the evening scan.

Crypto: CoinGecko market_chart (daily closes; no OHLC on the free tier, so the
strategy uses close-to-close ranges for those symbols).
Stocks: Yahoo Finance chart API (full daily OHLC, no key).

Same contract as fetch_prices: public endpoints only, disk cache, raw payload
snapshotted into the evidence dir with its SHA-256. On any failure returns
([], None) — the loop must never crash because a feed is down.
"""
from __future__ import annotations

import datetime as dt
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import universe as universe_mod
from .receipts import Receipt, hash_bytes, utcnow_iso

COINGECKO_MARKET_CHART = "https://api.coingecko.com/api/v3/coins/{id}/market_chart"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HISTORY_CACHE_TTL_S = 6 * 3600  # refresh a few times a day at most
HISTORY_DAYS = 90


@dataclass
class Bar:
    date: str   # YYYY-MM-DD
    open: float
    high: float
    low: float
    close: float

    @property
    def daily_range(self) -> float:
        return self.high - self.low


def _snapshot(raw: bytes, url: str, evidence_dir: Path, prefix: str, note: str) -> Receipt | None:
    digest = hash_bytes(raw)
    snap_path = evidence_dir / f"{prefix}_{digest[:16]}.json"
    try:
        snap_path.write_bytes(raw)
    except OSError:
        return None
    return Receipt(
        type=f"{prefix}_history_snapshot",
        source=url,
        observed_at=utcnow_iso(),
        sha256=digest,
        payload_path=str(snap_path),
        note=note,
    )


def _cached(cache_dir: Path, key: str) -> Path:
    digest = hash_bytes(key.encode())[:12]
    return cache_dir / f"history_{digest}.json"


def _get(url: str, cache_file: Path) -> bytes | None:
    if cache_file.exists() and time.time() - cache_file.stat().st_mtime < HISTORY_CACHE_TTL_S:
        try:
            return cache_file.read_bytes()
        except OSError:
            pass
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LeanTrader-Bot/paper"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read()
    except Exception:
        return None
    try:
        cache_file.write_bytes(raw)
    except OSError:
        pass
    return raw


def fetch_daily_bars(
    symbol: str,
    universe: list = universe_mod.WATCHLIST,
    cache_dir: str | Path = "paper/cache",
    evidence_dir: str | Path = "paper/evidence",
) -> tuple[list[Bar], Receipt | None]:
    """Daily bars for one symbol, oldest-first. ([], None) on any failure."""
    cache_dir = Path(cache_dir)
    evidence_dir = Path(evidence_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    try:
        asset = universe_mod.by_symbol(symbol, universe)
    except KeyError:
        return [], None

    if asset.coingecko_id:
        return _crypto_bars(asset, cache_dir, evidence_dir)
    if asset.yahoo_symbol:
        return _stock_bars(asset, cache_dir, evidence_dir)
    return [], None


def _crypto_bars(asset, cache_dir: Path, evidence_dir: Path):
    url = COINGECKO_MARKET_CHART.format(id=asset.coingecko_id) + "?" + urllib.parse.urlencode(
        {"vs_currency": "usd", "days": HISTORY_DAYS, "interval": "daily"}
    )
    raw = _get(url, _cached(cache_dir, "gecko:" + asset.coingecko_id))
    if not raw:
        return [], None
    receipt = _snapshot(raw, url, evidence_dir, "gecko", f"{asset.symbol} daily closes")
    try:
        points = json.loads(raw)["prices"]
    except (ValueError, KeyError):
        return [], receipt
    bars = []
    for ts_ms, close in points:
        if not isinstance(close, (int, float)) or close <= 0:
            continue
        day = dt.datetime.fromtimestamp(ts_ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d")
        # Free tier gives closes only; range is approximated from
        # close-to-close moves by the strategy.
        bars.append(Bar(date=day, open=close, high=close, low=close, close=float(close)))
    # de-dupe days, keep last
    seen: dict[str, Bar] = {}
    for b in bars:
        seen[b.date] = b
    return sorted(seen.values(), key=lambda b: b.date), receipt


def _stock_bars(asset, cache_dir: Path, evidence_dir: Path):
    url = YAHOO_CHART.format(symbol=asset.yahoo_symbol) + "?" + urllib.parse.urlencode(
        {"interval": "1d", "range": "6mo"}
    )
    raw = _get(url, _cached(cache_dir, "yahoo:" + asset.yahoo_symbol))
    if not raw:
        return [], None
    receipt = _snapshot(raw, url, evidence_dir, "yahoo", f"{asset.symbol} daily OHLC")
    try:
        result = json.loads(raw)["chart"]["result"][0]
        stamps = result["timestamp"]
        q = result["indicators"]["quote"][0]
    except (ValueError, KeyError, IndexError, TypeError):
        return [], receipt
    bars = []
    for i, ts in enumerate(stamps):
        try:
            o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        except (IndexError, TypeError):
            continue
        if not all(isinstance(v, (int, float)) and v > 0 for v in (o, h, l, c)):
            continue
        day = dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d")
        bars.append(Bar(date=day, open=o, high=h, low=l, close=c))
    seen: dict[str, Bar] = {}
    for b in bars:
        seen[b.date] = b
    return sorted(seen.values(), key=lambda b: b.date), receipt
