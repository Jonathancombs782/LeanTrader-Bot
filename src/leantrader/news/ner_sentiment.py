from __future__ import annotations

from typing import Dict, List


def _simple_keywords() -> Dict[str, List[str]]:
    return {
        "XAUUSD": ["gold", "xau", "safe haven"],
        "EURUSD": ["euro", "ecb", "eur"],
        "GBPUSD": ["boe", "pound", "sterling", "gbp"],
        "USDJPY": ["boj", "yen", "jpy"],
        "BTCUSDT": ["bitcoin", "btc", "crypto"],
    }


def tag_symbols(title: str) -> List[str]:
    t = title.lower()
    tags: List[str] = []
    for sym, kws in _simple_keywords().items():
        if any(k in t for k in kws):
            tags.append(sym)
    return tags


def sentiment_score(text: str) -> float:
    # Try VADER, fallback to naive
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer  # type: ignore

        a = SentimentIntensityAnalyzer()
        s = a.polarity_scores(text)
        return float(s.get("compound", 0.0))
    except Exception:
        pass
    text = text.lower()
    pos = sum(text.count(w) for w in ("beat", "bull", "up", "gain", "surge", "strong"))
    neg = sum(text.count(w) for w in ("miss", "bear", "down", "drop", "weak"))
    total = pos + neg
    return (pos - neg) / float(total) if total else 0.0
