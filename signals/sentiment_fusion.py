from __future__ import annotations

import hashlib
import os
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple


# ---------- ingest stubs (mock-friendly) ----------


def ingest_news(feed_urls: List[str]) -> List[Dict[str, Any]]:
    """Return normalized events: {ts, asset, source='news', text}.

    In mock mode (default), returns empty list. Caller can feed synthetic events in tests.
    """
    if not feed_urls or os.getenv("NEWS_API_KEY") is None:
        return []
    # Real implementation would fetch and parse feeds
    return []


def ingest_twitter(handles_or_keywords: List[str]) -> List[Dict[str, Any]]:
    if not handles_or_keywords or not os.getenv("TWITTER_BEARER_TOKEN"):
        return []
    return []


def ingest_telegram(channels: List[str]) -> List[Dict[str, Any]]:
    if not channels or not os.getenv("TELEGRAM_BOT_TOKEN"):
        return []
    return []


def ingest_onchain(tokens: List[str]) -> List[Dict[str, Any]]:
    # Could pull from lt_plugins/web3_signals or on-chain APIs; mock default
    return []


# ---------- sentiment scoring ----------


_POS = re.compile(r"\b(bull|breakout|pump|surge|upgrade|gain|positive|beat)\b", re.I)
_NEG = re.compile(r"\b(bear|dump|rug|crash|downgrade|loss|negative|miss)\b", re.I)


def sentiment_score(event: Dict[str, Any]) -> Tuple[float, float]:
    """Heuristic sentiment score in [-1,1] with a confidence in [0,1].

    Uses keyword matching; source can modulate confidence.
    """
    text = str(event.get("text") or "")
    if not text:
        return 0.0, 0.2
    pos = len(_POS.findall(text))
    neg = len(_NEG.findall(text))
    raw = pos - neg
    score = max(-1.0, min(1.0, raw / 3.0))
    src = (event.get("source") or "").lower()
    base_conf = 0.4
    if src == "onchain":
        base_conf = 0.8
    elif src == "twitter":
        base_conf = 0.6
    elif src == "telegram":
        base_conf = 0.5
    elif src == "news":
        base_conf = 0.5
    conf = max(0.1, min(1.0, base_conf * (1.0 + 0.1 * abs(raw))))
    return float(score), float(conf)


# ---------- fusion model ----------


@dataclass
class FusionModel:
    window_sec: int = 3600
    weights: Dict[str, float] = field(default_factory=lambda: {"onchain": 1.0, "twitter": 0.7, "news": 0.5, "telegram": 0.6})
    half_life_sec: int = 900

    def __post_init__(self):
        self._events: Deque[Tuple[int, str, float, float, str]] = deque()  # (ts, asset, score, conf, source)
        self._dedup: Dict[str, int] = {}

    def _alpha(self) -> float:
        # EWMA alpha derived from half-life
        import math

        h = max(1.0, float(self.half_life_sec))
        decay = math.exp(-math.log(2.0) / h)
        return 1.0 - decay

    def update(self, event: Dict[str, Any]) -> None:
        ts = int(event.get("ts") or int(time.time()))
        asset = (event.get("asset") or event.get("symbol") or "").upper()
        if not asset:
            return
        key = hashlib.sha1((asset + (event.get("text") or "")).encode("utf-8")).hexdigest()
        # de-dup within window
        self._gc(ts)
        if key in self._dedup:
            return
        score, conf = sentiment_score(event)
        src = (event.get("source") or "").lower()
        self._events.append((ts, asset, score, conf, src))
        self._dedup[key] = ts

    def _gc(self, now_ts: int) -> None:
        cutoff = now_ts - int(self.window_sec)
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()
        # remove old dedup entries
        for k, t0 in list(self._dedup.items()):
            if t0 < cutoff:
                self._dedup.pop(k, None)

    def features(self, when_ts: Optional[int], asset: str) -> Dict[str, float]:
        if when_ts is None:
            when_ts = int(time.time())
        self._gc(int(when_ts))
        a = self._alpha()
        s_val = 0.0
        s_conf = 0.0
        buzz = 0.0
        asset = asset.upper()
        for ts, sym, sc, cf, src in reversed(self._events):
            if sym != asset:
                continue
            w_src = float(self.weights.get(src, 0.5))
            # EWMA update
            s_val = a * (sc * w_src) + (1 - a) * s_val
            s_conf = a * (cf * w_src) + (1 - a) * s_conf
            buzz += 1.0 * w_src
        return {"sentiment": float(s_val), "sentiment_conf": float(min(1.0, s_conf)), "buzz": float(buzz)}


def output_features(when_ts: int, asset: str, model: FusionModel) -> Dict[str, float]:
    return model.features(when_ts, asset)


__all__ = [
    "ingest_news",
    "ingest_twitter",
    "ingest_telegram",
    "ingest_onchain",
    "sentiment_score",
    "FusionModel",
    "output_features",
]

