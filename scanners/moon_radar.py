from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


try:
    from prometheus_client import Gauge  # type: ignore

    MOON_RADAR_SCORE = Gauge(
        "moon_radar_score",
        "Moon Radar candidate score",
        ["asset", "category"],
    )
except Exception:  # pragma: no cover
    class _Noop:
        def labels(self, *_: Any, **__: Any) -> "_Noop":
            return self

        def set(self, *_: Any, **__: Any) -> None:
            pass

    MOON_RADAR_SCORE = _Noop()  # type: ignore


# Data inputs (file-based; no network here)
ENV_VOL = "MOON_VOL_PATH"  # {asset:{value,ts}}
ENV_WALLETS = "MOON_NEW_WALLETS_PATH"  # {asset:{value,ts}}
ENV_STARS = "MOON_STARS_PATH"  # {repo or asset:{value,ts}}
ENV_TRENDS = "MOON_TRENDS_PATH"  # {asset:{value,ts}}
ENV_LISTINGS = "MOON_LISTINGS_PATH"  # {asset:{value,ts}} rumor score
ENV_CATMAP = "MOON_CATEGORY_MAP_PATH"  # {asset: 'L2'|'RWA'|'MEME'|'AI'|'GAME'|...}
ENV_CATBOOST = "MOON_CATEGORY_BOOSTS_PATH"  # {category: boost_multiplier}

HISTORY = Path("runtime/moon_radar.json")


def _load_value_map(path: Optional[str]) -> Dict[str, Dict[str, float]]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: Dict[str, Dict[str, float]] = {}
    if isinstance(data, dict):
        for k, v in data.items():
            try:
                if isinstance(v, dict):
                    val = float(v.get("value") or v.get("count") or 0.0)
                    ts = float(v.get("ts") or 0.0)
                else:
                    val = float(v)
                    ts = 0.0
                out[str(k).upper()] = {"value": val, "ts": ts}
            except Exception:
                continue
    return out


def _zscore(values: Mapping[str, float]) -> Dict[str, float]:
    xs = [float(v) for v in values.values()]
    if len(xs) < 2:
        return {k: 0.0 for k in values.keys()}
    mean = statistics.fmean(xs)
    st = statistics.pstdev(xs) or 0.0
    if st <= 0:
        return {k: 0.0 for k in values.keys()}
    return {k: (float(v) - mean) / st for k, v in values.items()}


DEFAULT_WEIGHTS = {
    "volume": 0.30,
    "wallets": 0.25,
    "trends": 0.20,
    "stars": 0.15,
    "listings": 0.10,
}


DEFAULT_CATMAP = {
    "BTC": "L1",
    "ETH": "L1",
    "SOL": "L1",
    "ARB": "L2",
    "OP": "L2",
    "WIF": "MEME",
    "DOGE": "MEME",
    "TAO": "AI",
}


def _load_catmap(path: Optional[str]) -> Dict[str, str]:
    cm = dict(DEFAULT_CATMAP)
    if not path:
        return cm
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        for k, v in (d or {}).items():
            cm[str(k).upper()] = str(v)
    except Exception:
        pass
    return cm


def _load_catboosts(path: Optional[str]) -> Dict[str, float]:
    if not path:
        return {}
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return {str(k): float(v) for k, v in (d or {}).items()}
    except Exception:
        return {}


def _persist(history: Dict[str, Any]) -> None:
    try:
        HISTORY.parent.mkdir(parents=True, exist_ok=True)
        HISTORY.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _load_history() -> Dict[str, Any]:
    try:
        if HISTORY.exists():
            return json.loads(HISTORY.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}


def _confidence(sources_present: int) -> float:
    # scale confidence by number of sources with non-zero zscore
    return min(1.0, 0.3 + 0.2 * max(0, sources_present))


def scan_moon_radar() -> Dict[str, Any]:
    vol = _load_value_map(os.getenv(ENV_VOL, ""))
    wallets = _load_value_map(os.getenv(ENV_WALLETS, ""))
    stars = _load_value_map(os.getenv(ENV_STARS, ""))
    trends = _load_value_map(os.getenv(ENV_TRENDS, ""))
    listings = _load_value_map(os.getenv(ENV_LISTINGS, ""))
    catmap = _load_catmap(os.getenv(ENV_CATMAP, ""))
    catboost = _load_catboosts(os.getenv(ENV_CATBOOST, ""))

    # unify asset space
    assets = set().union(vol.keys(), wallets.keys(), stars.keys(), trends.keys(), listings.keys(), catmap.keys())
    # compute zscores across assets for each source
    z_vol = _zscore({a: vol.get(a, {}).get("value", 0.0) for a in assets})
    z_wallets = _zscore({a: wallets.get(a, {}).get("value", 0.0) for a in assets})
    z_trends = _zscore({a: trends.get(a, {}).get("value", 0.0) for a in assets})
    z_stars = _zscore({a: stars.get(a, {}).get("value", 0.0) for a in assets})
    z_listings = _zscore({a: listings.get(a, {}).get("value", 0.0) for a in assets})

    w = DEFAULT_WEIGHTS
    history = _load_history()
    prev_scores: Dict[str, float] = (history.get("scores") or {})

    scores: Dict[str, float] = {}
    detail: Dict[str, Dict[str, float]] = {}
    for a in assets:
        parts = {
            "volume": z_vol.get(a, 0.0),
            "wallets": z_wallets.get(a, 0.0),
            "trends": z_trends.get(a, 0.0),
            "stars": z_stars.get(a, 0.0),
            "listings": z_listings.get(a, 0.0),
        }
        score_now = sum(parts[k] * w[k] for k in w)
        # category boost
        score_now *= float(catboost.get(catmap.get(a, ""), 1.0))
        # persistence: EMA with alpha=0.3
        prev = float(prev_scores.get(a, 0.0))
        score = 0.7 * prev + 0.3 * score_now
        scores[a] = score
        detail[a] = parts

        try:
            MOON_RADAR_SCORE.labels(asset=a, category=catmap.get(a, "?")).set(float(score))
        except Exception:
            pass

    # build category momentum
    cat_scores: Dict[str, float] = {}
    for a, s in scores.items():
        cat = catmap.get(a, "?")
        cat_scores[cat] = cat_scores.get(cat, 0.0) + float(s)

    # watchlist: top assets with safety requirements
    try:
        from scanners.hype_radar import early_entry_filter, EntryThresholds  # type: ignore

        thr = EntryThresholds()
    except Exception:
        early_entry_filter = None  # type: ignore
        thr = None  # type: ignore

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    watch: List[Dict[str, Any]] = []
    for a, s in ranked[: 20]:
        parts = detail.get(a, {})
        nsrc = sum(1 for v in parts.values() if abs(float(v)) > 0.5)
        conf = _confidence(nsrc)
        item: Dict[str, Any] = {
            "asset": a,
            "category": catmap.get(a, "?"),
            "score": float(s),
            "confidence": conf,
            "parts": parts,
        }
        if early_entry_filter is not None:
            filt = early_entry_filter(a, thr)
            item["safety"] = filt
        watch.append(item)

    # category persistence
    prev_cats: Dict[str, float] = (history.get("categories") or {})
    cats_ema: Dict[str, float] = {}
    for k, v in cat_scores.items():
        p = float(prev_cats.get(k, 0.0))
        cats_ema[k] = 0.6 * p + 0.4 * float(v)

    out = {
        "ts": int(time.time()),
        "scores": scores,
        "details": detail,
        "categories": cats_ema,
        "watchlist": watch,
    }
    _persist(out)
    return out


def propose_pilots_from_moon(top_k: int = 5, per_asset_cap_usd: float = 500.0, total_cap_usd: float = 2000.0) -> List[Dict[str, Any]]:
    try:
        from scanners.hype_radar import propose_pilots  # type: ignore

        data = _load_history() or {}
        scores = data.get("scores") or {}
        return propose_pilots(scores, top_k=top_k, per_asset_cap_usd=per_asset_cap_usd, total_cap_usd=total_cap_usd)
    except Exception:
        return []


def main() -> int:
    p = argparse.ArgumentParser(description="Moon Radar: anomaly-driven emerging category watchlist")
    p.add_argument("--once", action="store_true")
    p.add_argument("--pilots", action="store_true")
    args = p.parse_args()
    out = scan_moon_radar()
    print(json.dumps({"top": list(sorted(out["scores"].items(), key=lambda kv: kv[1], reverse=True)[:10])}))
    if args.pilots:
        picks = propose_pilots_from_moon()
        print(json.dumps({"pilots": picks}))
    return 0


__all__ = ["MOON_RADAR_SCORE", "scan_moon_radar", "propose_pilots_from_moon"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
