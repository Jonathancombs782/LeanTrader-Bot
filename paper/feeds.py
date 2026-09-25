"""Public price feeds. No keys, no accounts — just public endpoints.

Every response is cached on disk and the raw payload is snapshotted into the
evidence dir with its SHA-256, so a signal can cite the exact bytes it saw.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import universe as universe_mod
from .receipts import Receipt, hash_bytes, utcnow_iso

COINGECKO_SIMPLE = "https://api.coingecko.com/api/v3/simple/price"
CACHE_TTL_S = 300


def _cache_path(cache_dir: Path) -> Path:
    return cache_dir / "coingecko_simple.json"


def fetch_prices(
    symbols: list[str] | None = None,
    universe: list = universe_mod.BLUE_CHIPS,
    cache_dir: str | Path = "paper/cache",
    evidence_dir: str | Path = "paper/evidence",
) -> tuple[dict[str, float], Receipt | None]:
    """Fetch USD mids from CoinGecko's free endpoint.

    Returns (prices, receipt). On any failure returns ({}, None) — the engine
    must never crash because a feed is down.
    """
    cache_dir = Path(cache_dir)
    evidence_dir = Path(evidence_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    wanted = [a for a in universe if a.coingecko_id and (symbols is None or a.symbol in symbols)]
    if not wanted:
        return {}, None
    ids = ",".join(a.coingecko_id for a in wanted)
    url = COINGECKO_SIMPLE + "?" + urllib.parse.urlencode(
        {"ids": ids, "vs_currencies": "usd"}
    )

    # short disk cache to respect the free rate limit
    cache_file = _cache_path(cache_dir)
    if cache_file.exists() and time.time() - cache_file.stat().st_mtime < CACHE_TTL_S:
        try:
            raw = cache_file.read_bytes()
            receipt = _snapshot_receipt(raw, url, evidence_dir, note="served from cache")
            return _extract(json.loads(raw), wanted), receipt
        except (OSError, ValueError):
            pass

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LeanTrader-Bot/paper"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
    except Exception:
        return {}, None

    try:
        cache_file.write_bytes(raw)
    except OSError:
        pass
    receipt = _snapshot_receipt(raw, url, evidence_dir, note=f"{len(wanted)} ids requested")
    try:
        data = json.loads(raw)
    except ValueError:
        return {}, receipt
    return _extract(data, wanted), receipt


def _snapshot_receipt(
    raw: bytes, url: str, evidence_dir: Path, note: str
) -> Receipt | None:
    stamp = utcnow_iso().replace(":", "").replace("+", "Z")
    snap_path = evidence_dir / f"coingecko_{stamp}.json"
    try:
        snap_path.write_bytes(raw)
    except OSError:
        return None
    return Receipt(
        type="coingecko_price_snapshot",
        source=url,
        observed_at=utcnow_iso(),
        sha256=hash_bytes(raw),
        payload_path=str(snap_path),
        note=note,
    )


def _extract(data: dict, wanted: list) -> dict[str, float]:
    prices: dict[str, float] = {}
    for asset in wanted:
        px = (data.get(asset.coingecko_id) or {}).get("usd")
        if isinstance(px, (int, float)) and px > 0:
            prices[asset.symbol] = float(px)
    return prices
