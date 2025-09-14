# learner.py
"""Small, conservative learner to turn news & historical signals into a simple model.

This is a lightweight proof-of-concept: it creates a TF-IDF vectorizer over titles+summaries
and fits a logistic regression to predict 'side' from historical signals if they exist.

Usage: .venv/Scripts/python tools/learner.py

This does NOT enable live trading. Models are saved under runtime/models.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

try:
    import joblib
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
except Exception:
    TfidfVectorizer = None
    LogisticRegression = None
    joblib = None


def _load_news_texts(limit: int = 1000) -> List[str]:
    p = Path("runtime") / "news"
    texts = []
    if not p.exists():
        return texts
    for f in p.glob("*.ndjson"):
        try:
            with f.open("r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        j = json.loads(line)
                        texts.append((j.get("title", "") + " " + j.get("summary", "")).strip())
                    except Exception:
                        continue
                    if len(texts) >= limit:
                        return texts
        except Exception:
            continue
    return texts


def _load_signals(limit: int = 2000):
    # load historical published signals to use as labels (buy=1 sell=0)
    p = Path("runtime")
    signals = []
    for f in p.glob("signals-*.ndjson"):
        try:
            with f.open("r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        j = json.loads(line)
                        if j.get("side") in ("buy", "sell"):
                            signals.append(j)
                    except Exception:
                        continue
                    if len(signals) >= limit:
                        return signals
        except Exception:
            continue
    return signals


def train_simple_model():
    if TfidfVectorizer is None:
        raise RuntimeError("scikit-learn and joblib required: pip install scikit-learn joblib")
    texts = _load_news_texts(2000)
    if not texts:
        print("No news texts found under runtime/news/. Run tools/run_crawler.py first.")
        return
    signals = _load_signals(2000)
    if not signals:
        print("No historical signals found under runtime/signals-*.ndjson. Model will be unsupervised.")
    # build corpus from news texts
    corpus = texts
    vect = TfidfVectorizer(max_features=4000, stop_words="english")
    X = vect.fit_transform(corpus)
    model = None
    if signals:
        # naive mapping: attempt to correlate last signal's side with last news items (very rough)
        # create labels from signals (buy->1, sell->0) for the same count as texts if possible
        labels = []
        for s in signals[: X.shape[0]]:
            labels.append(1 if s.get("side") == "buy" else 0)
        if len(labels) < X.shape[0]:
            labels = labels + [0] * (X.shape[0] - len(labels))
        clf = LogisticRegression(max_iter=200)
        try:
            clf.fit(X, labels)
            model = clf
        except Exception as e:
            print("Model training failed:", e)
    # persist
    outdir = Path("runtime") / "models"
    outdir.mkdir(parents=True, exist_ok=True)
    if model is not None:
        joblib.dump({"vect": vect, "clf": model}, outdir / "news_model.pkl")
        print("Saved model to runtime/models/news_model.pkl")
    else:
        joblib.dump({"vect": vect, "clf": None}, outdir / "news_model_partial.pkl")
        print("Saved vectorizer to runtime/models/news_model_partial.pkl")


if __name__ == "__main__":
    train_simple_model()
