from __future__ import annotations

import time

from signals.sentiment_fusion import FusionModel, sentiment_score, output_features


def test_sentiment_scoring_keywords():
    s, c = sentiment_score({"text": "Bullish breakout on BTC", "source": "twitter"})
    assert s > 0
    assert 0.0 <= c <= 1.0
    s2, c2 = sentiment_score({"text": "bear rug crash", "source": "news"})
    assert s2 < 0


def test_fusion_model_features():
    m = FusionModel(window_sec=3600)
    now = int(time.time())
    m.update({"ts": now, "asset": "BTCUSDT", "source": "twitter", "text": "Bull breakout"})
    m.update({"ts": now, "asset": "BTCUSDT", "source": "news", "text": "upgrade positive"})
    feats = output_features(now, "BTCUSDT", m)
    assert "sentiment" in feats and "buzz" in feats
    assert feats["buzz"] > 0

