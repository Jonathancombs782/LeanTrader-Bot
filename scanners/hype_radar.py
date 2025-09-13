from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


# ---- Metrics ---------------------------------------------------------------
try:
    from prometheus_client import Gauge  # type: ignore

    HYPE_SCORE = Gauge(
        "hype_score",
        "Composite hype score per asset (weighted z-scores with decay)",
        ["asset"],
    )
except Exception:  # pragma: no cover
    class _Noop:
        def labels(self, *_: Any, **__: Any) -> "_Noop":
            return self

        def set(self, *_: Any, **__: Any) -> None:
            pass

    HYPE_SCORE = _Noop()  # type: ignore


# ---- Helpers ---------------------------------------------------------------

def _now() -> float:
    return time.time()


def _load_json(path: str) -> Any:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _zscore_map(values: Mapping[str, float]) -> Dict[str, float]:
    xs = [float(v) for v in values.values() if v is not None]
    if len(xs) < 2:
        return {k: 0.0 for k in values.keys()}
    mean = statistics.fmean(xs)
    stdev = statistics.pstdev(xs) or 0.0
    if stdev <= 0:
        return {k: 0.0 for k in values.keys()}
    return {k: (float(v) - mean) / stdev for k, v in values.items()}


def _decay(ts: Optional[float], half_life_days: float = 3.0) -> float:
    if not ts:
        return 1.0
    dt_days = max(0.0, (_now() - float(ts)) / 86400.0)
    return 0.5 ** (dt_days / max(1e-6, half_life_days))


# ---- Trend sources (file-driven, API-agnostic) -----------------------------

ENV_TWITTER = "TWITTER_RATES_PATH"  # {asset: {value: float, ts: epoch}}
ENV_DISCORD = "DISCORD_VOLUME_PATH"  # {asset: {value: float, ts: epoch}}
ENV_TELEGRAM = "TELEGRAM_VOLUME_PATH"  # {asset: {value: float, ts: epoch}}
ENV_GITHUB = "GITHUB_COMMITS_PATH"  # {repo: {value: float, ts: epoch}}
ENV_REPO_MAP = "ASSET_REPO_MAP_PATH"  # {asset: ["owner/repo", ...]}
ENV_TRENDS = "GOOGLE_TRENDS_PATH"  # {asset: {value: float, ts: epoch}}
ENV_LIQ = "HYPE_LIQUIDITY_PATH"  # {asset: {usd_liquidity: float, ts: epoch}}
ENV_SAFETY = "TOKEN_SAFETY_PATH"  # {asset: {flagged: bool, risk_score: float}}
ENV_LISTING = "LISTING_PROB_PATH"  # {asset: {prob: float, ts: epoch}}


def _load_value_map(path: Optional[str]) -> Dict[str, Dict[str, float]]:
    if not path:
        return {}
    data = _load_json(path)
    if not isinstance(data, dict):
        return {}
    out: Dict[str, Dict[str, float]] = {}
    for k, v in data.items():
        try:
            if isinstance(v, dict):
                val = float(v.get("value") or v.get("count") or v.get("vol") or 0.0)
                ts = float(v.get("ts")) if v.get("ts") is not None else None
            else:
                val = float(v)
                ts = None
            out[str(k)] = {"value": val, "ts": ts or 0.0}
        except Exception:
            continue
    return out


def _repo_map(path: Optional[str], fallback: Optional[Mapping[str, Sequence[str]]] = None) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    if path:
        data = _load_json(path)
        if isinstance(data, dict):
            for k, v in data.items():
                try:
                    out[str(k)] = [str(x) for x in (v if isinstance(v, list) else [v])]
                except Exception:
                    continue
    if fallback:
        for k, v in fallback.items():
            out.setdefault(k, list(v))
    return out


def _github_values(asset_list: Sequence[str], repo_map: Mapping[str, Sequence[str]], commits: Mapping[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    # Sum commits across repos mapped to each asset
    out: Dict[str, Dict[str, float]] = {a: {"value": 0.0, "ts": 0.0} for a in asset_list}
    for asset in asset_list:
        ts = 0.0
        total = 0.0
        for repo in repo_map.get(asset, []):
            v = commits.get(repo)
            if not v:
                continue
            total += float(v.get("value", 0.0) or 0.0)
            ts = max(ts, float(v.get("ts", 0.0) or 0.0))
        out[asset] = {"value": total, "ts": ts}
    return out


@dataclass
class HypeWeights:
    twitter: float = 0.35
    community: float = 0.35  # discord + telegram
    github: float = 0.15
    trends: float = 0.15

    def normalize(self) -> "HypeWeights":
        s = self.twitter + self.community + self.github + self.trends
        if s <= 0:
            return self
        self.twitter /= s
        self.community /= s
        self.github /= s
        self.trends /= s
        return self


def hype_score(
    assets: Sequence[str],
    repo_map_fallback: Optional[Mapping[str, Sequence[str]]] = None,
    weights: Optional[HypeWeights] = None,
    half_life_days: float = 3.0,
) -> Dict[str, float]:
    assets = [a.upper() for a in assets]
    weights = (weights or HypeWeights()).normalize()

    tw = _load_value_map(os.getenv(ENV_TWITTER, "").strip())
    dc = _load_value_map(os.getenv(ENV_DISCORD, "").strip())
    tg = _load_value_map(os.getenv(ENV_TELEGRAM, "").strip())
    gh_repos = _repo_map(os.getenv(ENV_REPO_MAP, "").strip(), fallback=repo_map_fallback)
    gh_all = _load_value_map(os.getenv(ENV_GITHUB, "").strip())
    gh = _github_values(assets, gh_repos, gh_all)
    tr = _load_value_map(os.getenv(ENV_TRENDS, "").strip())

    # Compose community by summing discord+telegram
    community: Dict[str, Dict[str, float]] = {a: {"value": 0.0, "ts": 0.0} for a in assets}
    for a in assets:
        v1 = tw.get(a, {"value": 0.0, "ts": 0.0})
        v2 = dc.get(a, {"value": 0.0, "ts": 0.0})
        v3 = tg.get(a, {"value": 0.0, "ts": 0.0})
        community[a] = {"value": float(v2.get("value", 0.0)) + float(v3.get("value", 0.0)), "ts": max(float(v2.get("ts", 0.0)), float(v3.get("ts", 0.0)))}

    # z-scores per source
    z_tw = _zscore_map({a: tw.get(a, {}).get("value", 0.0) for a in assets})
    z_comm = _zscore_map({a: community.get(a, {}).get("value", 0.0) for a in assets})
    z_gh = _zscore_map({a: gh.get(a, {}).get("value", 0.0) for a in assets})
    z_tr = _zscore_map({a: tr.get(a, {}).get("value", 0.0) for a in assets})

    scores: Dict[str, float] = {}
    for a in assets:
        # Recency decay: max of the source timestamps for the asset
        ts = max(
            float(tw.get(a, {}).get("ts", 0.0) or 0.0),
            float(community.get(a, {}).get("ts", 0.0) or 0.0),
            float(gh.get(a, {}).get("ts", 0.0) or 0.0),
            float(tr.get(a, {}).get("ts", 0.0) or 0.0),
        )
        dec = _decay(ts, half_life_days=half_life_days)
        raw = (
            weights.twitter * z_tw.get(a, 0.0)
            + weights.community * z_comm.get(a, 0.0)
            + weights.github * z_gh.get(a, 0.0)
            + weights.trends * z_tr.get(a, 0.0)
        )
        scores[a] = float(raw * dec)
        try:
            HYPE_SCORE.labels(asset=a).set(scores[a])
        except Exception:
            pass
    return scores


# ---- Early-entry filter ----------------------------------------------------

@dataclass
class EntryThresholds:
    min_liquidity_usd: float = 1_000_000.0
    max_risk_score: float = 0.6  # 0..1, lower better
    min_listing_prob: float = 0.2


def early_entry_filter(asset: str, thr: Optional[EntryThresholds] = None) -> Dict[str, Any]:
    thr = thr or EntryThresholds()
    liqu = _load_value_map(os.getenv(ENV_LIQ, "").strip())
    safety = _load_json(os.getenv(ENV_SAFETY, "").strip()) or {}
    listing = _load_value_map(os.getenv(ENV_LISTING, "").strip())

    a = asset.upper()
    reasons: List[str] = []
    passed = True

    L = float((liqu.get(a) or {}).get("usd_liquidity") or (liqu.get(a) or {}).get("value") or 0.0)
    if L < float(thr.min_liquidity_usd):
        passed = False
        reasons.append(f"liquidity<{thr.min_liquidity_usd}")

    s = safety.get(a) if isinstance(safety, dict) else None
    flagged = bool((s or {}).get("flagged", False))
    risk_score = float((s or {}).get("risk_score", 0.0) or 0.0)
    if flagged or risk_score > thr.max_risk_score:
        passed = False
        if flagged:
            reasons.append("flagged")
        if risk_score > thr.max_risk_score:
            reasons.append(f"risk>{thr.max_risk_score}")

    p = float((listing.get(a) or {}).get("prob") or (listing.get(a) or {}).get("value") or 0.0)
    if p < float(thr.min_listing_prob):
        reasons.append("low_listing_prob")
        # Low listing prob alone doesn’t block; it reduces priority for pilots.

    return {"pass": passed, "reasons": reasons, "liquidity_usd": L, "risk_score": risk_score, "listing_prob": p}


# ---- Pilot allocation suggestion ------------------------------------------

def propose_pilots(
    scores: Mapping[str, float],
    top_k: int = 10,
    per_asset_cap_usd: float = 1000.0,
    total_cap_usd: float = 5000.0,
    min_score: float = 0.5,
) -> List[Dict[str, Any]]:
    order = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    picks: List[Dict[str, Any]] = []
    budget = float(total_cap_usd)
    for a, sc in order[: max(1, top_k)]:
        filt = early_entry_filter(a)
        if not filt.get("pass"):
            continue
        if float(sc) < float(min_score):
            continue
        alloc = min(float(per_asset_cap_usd), budget)
        if alloc <= 0:
            break
        picks.append({"asset": a, "score": float(sc), "allocation_usd": float(alloc), "context": filt})
        budget -= alloc
        if budget <= 0:
            break
    return picks


# ---- CLI ------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Hype Radar: composite hype score from social + dev + trends")
    p.add_argument("--assets", default=os.getenv("HYPE_ASSETS", "BTC,ETH,SOL,XRP,DOGE"))
    p.add_argument("--repos", default=os.getenv(ENV_REPO_MAP, ""))
    p.add_argument("--out", default=os.getenv("HYPE_OUT", "runtime/hype_scores.json"))
    p.add_argument("--top", type=int, default=int(os.getenv("HYPE_TOP", "10")))
    p.add_argument("--pilots", action="store_true", help="print pilot allocations suggestion")
    args = p.parse_args()

    assets = [s.strip().upper() for s in args.assets.split(",") if s.strip()]
    repos_map = _repo_map(args.repos or None)
    scores = hype_score(assets, repo_map_fallback=repos_map)
    top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[: max(1, args.top)]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ts": int(time.time()), "scores": scores, "top": top}
    try:
        out_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

    print(json.dumps(top, ensure_ascii=False))

    if args.pilots:
        picks = propose_pilots(scores, top_k=args.top)
        print(json.dumps(picks, ensure_ascii=False))
    return 0


__all__ = [
    "HYPE_SCORE",
    "HypeWeights",
    "EntryThresholds",
    "hype_score",
    "early_entry_filter",
    "propose_pilots",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

