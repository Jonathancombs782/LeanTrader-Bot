"""Public price feeds. No keys, no accounts — just public endpoints.

Every response is cached on disk and the raw payload is snapshotted into the
evidence dir with its SHA-256, so a signal can cite the exact bytes it saw.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import universe as universe_mod
from .receipts import Receipt, hash_bytes, utcnow_iso

COINGECKO_SIMPLE = "https://api.coingecko.com/api/v3/simple/price"
CACHE_TTL_S = 300


def _epoch_to_iso(ts: int | float | None) -> str | None:
    if not isinstance(ts, (int, float)) or ts <= 0:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def _cache_path(cache_dir: Path, ids: str) -> Path:
    # Key the cache by the requested asset set: a SOL-only response must never
    # be served to a BTC request just because it is fresh.
    key = hashlib.sha256(ids.encode()).hexdigest()[:12]
    return cache_dir / f"coingecko_simple_{key}.json"


def fetch_prices(
    symbols: list[str] | None = None,
    universe: list = universe_mod.BLUE_CHIPS,
    cache_dir: str | Path = "paper/cache",
    evidence_dir: str | Path = "paper/evidence",
    with_marks: bool = False,
) -> tuple[dict[str, float], Receipt | None] | tuple[dict[str, float], dict, Receipt | None]:
    """Fetch USD mids from CoinGecko's free endpoint.

    Returns (prices, receipt). On any failure returns ({}, None) — the engine
    must never crash because a feed is down.

    With with_marks=True, returns (prices, marks, receipt) where marks maps
    each symbol to {"source_observed_at", "received_at"} (both ISO-8601 UTC):
    the provider's own update time for the quote, and when WE fetched the
    bytes. A cached quote keeps its original fetch time — a 4-minute-old
    cache hit is not restamped as fresh.
    """
    cache_dir = Path(cache_dir)
    evidence_dir = Path(evidence_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    wanted = [a for a in universe if a.coingecko_id and (symbols is None or a.symbol in symbols)]
    if not wanted:
        return ({}, None) if not with_marks else ({}, {}, None)
    ids = ",".join(a.coingecko_id for a in wanted)
    url = COINGECKO_SIMPLE + "?" + urllib.parse.urlencode(
        {"ids": ids, "vs_currencies": "usd", "include_last_updated_at": "true"}
    )

    def _marks(prices: dict[str, float], provider_ts: dict[str, int | None],
               received_at: str) -> dict:
        return {
            sym: {
                "source_observed_at": _epoch_to_iso(provider_ts.get(sym)),
                "received_at": received_at,
            }
            for sym in prices
        }

    # short disk cache to respect the free rate limit
    cache_file = _cache_path(cache_dir, ids)
    if cache_file.exists() and time.time() - cache_file.stat().st_mtime < CACHE_TTL_S:
        try:
            raw = cache_file.read_bytes()
            # Cache hit: the bytes were fetched at the file's mtime — that is
            # the true received_at, not now. Restamping it would make a stale
            # quote look fresh to the risk gates.
            received_at = datetime.fromtimestamp(
                cache_file.stat().st_mtime, timezone.utc
            ).isoformat(timespec="seconds")
            receipt = _snapshot_receipt(raw, url, evidence_dir, note="served from cache")
            prices, provider_ts = _extract(json.loads(raw), wanted)
            if with_marks:
                return prices, _marks(prices, provider_ts, received_at), receipt
            return prices, receipt
        except (OSError, ValueError):
            pass

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LeanTrader-Bot/paper"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
    except Exception:
        return ({}, None) if not with_marks else ({}, {}, None)

    received_at = utcnow_iso()
    try:
        cache_file.write_bytes(raw)
    except OSError:
        pass
    receipt = _snapshot_receipt(raw, url, evidence_dir, note=f"{len(wanted)} ids requested")
    try:
        data = json.loads(raw)
    except ValueError:
        return ({}, receipt) if not with_marks else ({}, {}, receipt)
    prices, provider_ts = _extract(data, wanted)
    if with_marks:
        return prices, _marks(prices, provider_ts, received_at), receipt
    return prices, receipt


def _snapshot_receipt(
    raw: bytes, url: str, evidence_dir: Path, note: str
) -> Receipt | None:
    # Content-addressed filename: one-second timestamps collide when two
    # fetches run in the same second, and the later write would invalidate the
    # earlier receipt's hash. Identical payloads safely share one file.
    digest = hash_bytes(raw)
    snap_path = evidence_dir / f"coingecko_{digest[:16]}.json"
    try:
        snap_path.write_bytes(raw)
    except OSError:
        return None
    return Receipt(
        type="coingecko_price_snapshot",
        source=url,
        observed_at=utcnow_iso(),
        sha256=digest,
        payload_path=str(snap_path),
        note=note,
    )


def _extract(data: dict, wanted: list) -> tuple[dict[str, float], dict[str, int | None]]:
    """Pull USD mids plus the provider's own last-updated timestamps.

    last_updated_at is CoinGecko's indexer refresh time for the quote — it
    bounds provider update age, not underlying exchange-tick freshness.
    """
    prices: dict[str, float] = {}
    provider_ts: dict[str, int | None] = {}
    for asset in wanted:
        entry = data.get(asset.coingecko_id) or {}
        px = entry.get("usd")
        if isinstance(px, (int, float)) and px > 0:
            prices[asset.symbol] = float(px)
            ts = entry.get("last_updated_at")
            provider_ts[asset.symbol] = int(ts) if isinstance(ts, (int, float)) else None
    return prices, provider_ts
