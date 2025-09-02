"""Lightweight trainer for simple models.

This module offers a minimal interface to train a scikit-learn model on
features derived from OHLCV CSVs saved by `market_data.py`. It is optional and
only runs if scikit-learn is present.
"""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import List

try:
    from sklearn.ensemble import RandomForestClassifier  # type: ignore
    from sklearn.model_selection import train_test_split  # type: ignore
    from sklearn.metrics import accuracy_score  # type: ignore
except Exception:
    RandomForestClassifier = None


def _model_dir() -> Path:
    p = Path("runtime") / "models"
    p.mkdir(parents=True, exist_ok=True)
    return p


def featurize_rows(rows: List[List[float]]) -> List[List[float]]:
    # rows: [ts, o, h, l, c, v]
    out = []
    for i in range(1, len(rows)):
        prev = rows[i - 1]
        cur = rows[i]
        ret = (cur[4] - prev[4]) / (prev[4] if prev[4] else 1.0)
        out.append([ret, (cur[2] - cur[3]), cur[5]])
    return out


def train_dummy_classifier(candles_csv_path: str) -> dict:
    if RandomForestClassifier is None:
        raise RuntimeError("scikit-learn is required for training")
    import csv

    rows = []
    with open(candles_csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        for r in reader:
            try:
                rows.append([int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])])
            except Exception:
                continue
    if len(rows) < 10:
        raise RuntimeError("not enough data to train")
    X = featurize_rows(rows)
    # simple label: next return > 0
    y = [1 if x[0] > 0 else 0 for x in X]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    clf = RandomForestClassifier(n_estimators=50, random_state=42)
    clf.fit(X_train, y_train)
    preds = clf.predict(X_test)
    acc = float(accuracy_score(y_test, preds))
    p = _model_dir() / f"rf_model_{int(__import__('time').time())}.pkl"
    with p.open("wb") as f:
        pickle.dump(clf, f)
    return {"model_path": str(p), "accuracy": acc}
