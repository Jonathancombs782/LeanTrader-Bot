from __future__ import annotations

import logging
import math
import statistics
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence


# Metrics: expose a Counter named ONCHAIN_SPIKES with a 'type' label.
try:
    from prometheus_client import Counter  # type: ignore

    ONCHAIN_SPIKES = Counter(
        "onchain_spikes_total",
        "Count of on-chain spike events detected",
        ["type"],
    )
except Exception:  # pragma: no cover - prometheus client may not be available
    class _NoopCounter:
        def labels(self, *_: Any, **__: Any) -> "_NoopCounter":
            return self

        def inc(self, *_: Any, **__: Any) -> None:
            pass

    ONCHAIN_SPIKES = _NoopCounter()  # type: ignore


def _get(d: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    """Return first present key from mapping.

    Example: _get(evt, "usd_value", "value_usd", default=0)
    """

    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def whale_transfer_detector(
    transfers: Sequence[Mapping[str, Any]],
    min_usd: float = 500_000.0,
) -> List[Dict[str, Any]]:
    """Detect large on-chain transfers ("whale" moves).

    Args:
        transfers: Sequence of transfer dicts. Expected keys (best effort):
            - token | asset | symbol: token identifier
            - usd_value | value_usd | amount_usd: transfer size in USD
              (alternatively: amount + price_usd)
            - direction: optional semantic direction (e.g., "in", "out", "unknown")
            - ts: optional timestamp
        min_usd: Minimum USD size to consider a whale transfer.

    Returns:
        List of event dicts: {type, token, size_usd, direction, ts}
    """

    events: List[Dict[str, Any]] = []
    for t in transfers or []:
        token = _get(t, "token", "asset", "symbol", default="?")
        usd = _get(t, "usd_value", "value_usd", "amount_usd")
        if usd is None:
            amt = _get(t, "amount", "size", default=None)
            price = _get(t, "price_usd", "usd_price", default=None)
            usd = (float(amt) * float(price)) if (amt is not None and price is not None) else None

        try:
            usd_val = float(usd) if usd is not None else None
        except Exception:
            logging.debug("Skipping transfer with non-numeric USD value: %r", usd)
            usd_val = None

        if usd_val is None or usd_val < float(min_usd):
            continue

        direction = str(_get(t, "direction", default="unknown")).lower()
        ts = _get(t, "ts", "timestamp", default=None)

        evt = {
            "type": "whale_transfer",
            "token": token,
            "size_usd": usd_val,
            "direction": direction,
            "ts": ts,
        }
        events.append(evt)
        try:
            ONCHAIN_SPIKES.labels(type="whale_transfer").inc()
        except Exception:
            pass

    return events


def pool_imbalance_detector(
    pools: Sequence[Mapping[str, Any]],
    threshold_pct: float = 10.0,
) -> List[Dict[str, Any]]:
    """Detect unusual reserve or balance shifts in liquidity pools.

    Args:
        pools: Sequence of pool snapshots with expected keys (best effort):
            - pool | pair: pool identifier
            - reserve0, reserve1: current reserves (numeric)
            - prev_reserve0, prev_reserve1: previous reserves (numeric)
            - token0, token1: optional token symbols
            - ts: optional timestamp
        threshold_pct: Percent threshold for significant change (e.g., 10 means 10%).

    Returns:
        List of event dicts summarizing imbalance/liquidity shifts per pool.
    """

    thr = float(threshold_pct)
    events: List[Dict[str, Any]] = []

    for p in pools or []:
        pool_name = _get(p, "pool", "pair", default="?")
        r0 = _get(p, "reserve0", default=None)
        r1 = _get(p, "reserve1", default=None)
        pr0 = _get(p, "prev_reserve0", default=None)
        pr1 = _get(p, "prev_reserve1", default=None)

        try:
            r0f = float(r0)
            r1f = float(r1)
            pr0f = float(pr0)
            pr1f = float(pr1)
        except Exception:
            # If we cannot parse reserves, skip this pool entry
            logging.debug("Skipping pool with invalid reserves: %s", pool_name)
            continue

        cur_total = r0f + r1f
        prev_total = pr0f + pr1f
        if prev_total <= 0 or cur_total <= 0:
            logging.debug("Skipping pool with non-positive totals: %s", pool_name)
            continue

        # Balance ratio change (0..1), measured on token0 share
        cur_ratio = r0f / cur_total
        prev_ratio = pr0f / prev_total
        ratio_delta_pct = abs(cur_ratio - prev_ratio) * 100.0

        # Total liquidity change
        liq_delta_pct = (cur_total - prev_total) / prev_total * 100.0
        liq_direction = "increase" if liq_delta_pct >= 0 else "decrease"

        significant = (ratio_delta_pct >= thr) or (abs(liq_delta_pct) >= thr)
        if not significant:
            continue

        ts = _get(p, "ts", "timestamp", default=None)
        token0 = _get(p, "token0", default=None)
        token1 = _get(p, "token1", default=None)

        evt = {
            "type": "pool_imbalance",
            "pool": pool_name,
            "delta_ratio_pct": ratio_delta_pct,
            "delta_liquidity_pct": liq_delta_pct,
            "direction": liq_direction,
            "assets": [token0, token1],
            "ts": ts,
        }
        events.append(evt)
        try:
            ONCHAIN_SPIKES.labels(type="pool_imbalance").inc()
        except Exception:
            pass

    return events


def dex_volume_spike(
    asset: str,
    volumes: Sequence[float],
    zscore_threshold: float = 3.0,
    window: int = 48,
) -> List[Dict[str, Any]]:
    """Detect sharp spikes in DEX trading volume via z-score.

    Args:
        asset: Asset or token identifier.
        volumes: Sequence of recent volume values ordered oldest->newest.
        zscore_threshold: Minimum z-score to qualify as a spike (default >= 3).
        window: Number of prior samples (excluding the last) to form baseline.

    Returns:
        Either empty list or a single event dict with statistics.
    """

    vals = [float(v) for v in (volumes or []) if v is not None]
    if len(vals) < max(5, window + 1):
        return []

    current = vals[-1]
    baseline = vals[-(window + 1) : -1] if len(vals) > window else vals[:-1]
    if len(baseline) < 3:
        return []

    mean = statistics.fmean(baseline)
    stdev = statistics.pstdev(baseline) if len(baseline) > 1 else 0.0
    if stdev <= 0:
        return []

    z = (current - mean) / stdev
    if z < float(zscore_threshold):
        return []

    evt = {
        "type": "dex_volume_spike",
        "asset": asset,
        "zscore": z,
        "volume": current,
        "baseline_mean": mean,
        "baseline_std": stdev,
        "window": len(baseline),
    }

    try:
        ONCHAIN_SPIKES.labels(type="dex_volume_spike").inc()
    except Exception:
        pass

    return [evt]


def sentiment_fusion(events: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, float]]:
    """Map on-chain events to coarse sentiment and buzz features.

    Heuristics (simple, sign-aware where possible):
      - whale_transfer: adds buzz; sentiment based on direction if provided
        ("in" -> bearish, "out" -> bullish, else neutral). Magnitude
        scales with log10(size_usd/100k).
      - pool_imbalance: adds buzz; liquidity increases are modestly bullish,
        decreases modestly bearish; magnitude scales with |delta_liquidity_pct|.
      - dex_volume_spike: adds buzz strongly; sentiment neutral (directionless).

    Returns:
        Mapping keyed by subject (token/asset/pool) with {buzz, sentiment}.
    """

    features: Dict[str, Dict[str, float]] = {}

    def add_feat(key: str, buzz: float = 0.0, sentiment: float = 0.0) -> None:
        if key not in features:
            features[key] = {"buzz": 0.0, "sentiment": 0.0}
        features[key]["buzz"] += float(buzz)
        features[key]["sentiment"] += float(sentiment)

    for e in events or []:
        etype = str(e.get("type", "")).lower()
        if etype == "whale_transfer":
            token = str(_get(e, "token", "asset", default="unknown")).upper()
            size = _get(e, "size_usd", default=0.0) or 0.0
            try:
                mag = max(0.0, math.log10(max(1.0, float(size) / 100_000.0)))
            except Exception:
                mag = 0.0
            direction = str(_get(e, "direction", default="unknown")).lower()
            dir_w = -0.3 if direction == "in" else (0.3 if direction == "out" else 0.0)
            add_feat(token, buzz=1.0 + mag, sentiment=dir_w * (1.0 + mag))

        elif etype == "pool_imbalance":
            pool = str(_get(e, "pool", default="unknown"))
            dliq = float(_get(e, "delta_liquidity_pct", default=0.0) or 0.0)
            direction = str(_get(e, "direction", default="unknown")).lower()
            sign = 1.0 if direction == "increase" else (-1.0 if direction == "decrease" else 0.0)
            buzz = 0.5 + min(5.0, abs(dliq) / 10.0)
            sentiment = sign * (abs(dliq) / 20.0)
            add_feat(pool, buzz=buzz, sentiment=sentiment)

        elif etype == "dex_volume_spike":
            asset = str(_get(e, "asset", default="unknown")).upper()
            z = float(_get(e, "zscore", default=0.0) or 0.0)
            buzz = 1.0 + min(10.0, z)  # strong buzz for large z
            add_feat(asset, buzz=buzz, sentiment=0.0)

        else:
            # Unknown event types do not contribute features
            continue

    return features


__all__ = [
    "ONCHAIN_SPIKES",
    "whale_transfer_detector",
    "pool_imbalance_detector",
    "dex_volume_spike",
    "sentiment_fusion",
]

