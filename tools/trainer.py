"""Lightweight trainer for simple models.

This module offers a minimal interface to train a scikit-learn model on
features derived from OHLCV CSVs saved by `market_data.py`. It is optional and
only runs if scikit-learn is present.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Dict, List, Optional

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


def _model_meta_path(model_path: Path) -> Path:
    return model_path.with_suffix(model_path.suffix + ".meta.json")


def featurize_rows(rows: List[List[float]]) -> List[List[float]]:
    # rows: [ts, o, h, l, c, v]
    out = []
    for i in range(1, len(rows)):
        prev = rows[i - 1]
        cur = rows[i]
        ret = (cur[4] - prev[4]) / (prev[4] if prev[4] else 1.0)
        out.append([ret, (cur[2] - cur[3]), cur[5]])
    return out


def _save_model_and_meta(clf, meta: Dict[str, object]) -> Dict[str, object]:
    p = _model_dir() / f"rf_model_{int(__import__('time').time())}.pkl"
    with p.open("wb") as f:
        pickle.dump(clf, f)
    meta_path = _model_meta_path(p)
    try:
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception:
        # non-fatal if metadata can't be written
        pass
    # retention: keep only latest N models to avoid unbounded disk use
    try:
        import os
        keep = int(os.getenv('MODEL_RETENTION', '5'))
        models = sorted(_model_dir().glob('rf_model_*.pkl'), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in models[keep:]:
            try:
                old_meta = _model_meta_path(old)
                # record deletion in a small audit log
                try:
                    logp = Path('runtime') / 'logs' / 'model_retention.log'
                    logp.parent.mkdir(parents=True, exist_ok=True)
                    with logp.open('a', encoding='utf-8') as lf:
                        lf.write(f"DELETE\t{int(__import__('time').time())}\t{old}\n")
                except Exception:
                    pass
                old.unlink()
                if old_meta.exists():
                    old_meta.unlink()
            except Exception:
                continue
    except Exception:
        pass
    return {"model_path": str(p), "meta_path": str(meta_path)}


def train_dummy_classifier(candles_csv_path: str) -> Dict[str, object]:
    if RandomForestClassifier is None:
        raise RuntimeError("scikit-learn is required for training")
    import csv

    rows: List[List[float]] = []
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
    meta = {
        "created_at": int(__import__("time").time()),
        "accuracy": acc,
        "n_samples": len(rows),
        "features": ["ret", "range", "volume"],
    }
    saved = _save_model_and_meta(clf, meta)
    return {"model_path": saved.get("model_path"), "meta_path": saved.get("meta_path"), "accuracy": acc}


def load_model(path: str):
    """Load a pickled model from disk and return it. Raises on failure."""
    p = Path(path)
    with p.open("rb") as f:
        return pickle.load(f)
