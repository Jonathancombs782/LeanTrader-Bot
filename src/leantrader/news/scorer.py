from __future__ import annotations

import math
from typing import Dict, List

from .feeds import NewsItem
from .ner_sentiment import sentiment_score, tag_symbols


def score_by_symbol(items: List[NewsItem], now_ts: float) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for it in items:
        syms = tag_symbols(it.title)
        if not syms:
            continue
        sent = sentiment_score(it.title)
        age_min = max(0.0, (now_ts - it.ts) / 60.0)
        decay = math.exp(-age_min / 180.0)  # 3h half-life approx
        for s in syms:
            scores[s] = scores.get(s, 0.0) + sent * decay
    # map to 0..1 via sigmoid-ish function
    out: Dict[str, float] = {}
    for s, v in scores.items():
        out[s] = 1.0 / (1.0 + math.exp(-v))
    return out
