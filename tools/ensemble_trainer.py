"""Train and persist a simple RandomForest ensemble from feature CSVs."""
from __future__ import annotations

import os
import time
import pickle
from pathlib import Path
from typing import List

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

from tools.featurizer import build_features_and_labels, sample_paths_from_data_dir


MODEL_DIR = Path("runtime") / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def train_ensemble_from_dir(data_dir: str) -> dict:
    paths = sample_paths_from_data_dir(data_dir)
    if not paths:
        raise RuntimeError("no CSV data found to train on")
    all_acc = []
    models = []
    for p in paths:
        X, y = build_features_and_labels(p)
        if len(y) < 10:
            continue
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        clf = RandomForestClassifier(n_estimators=50, random_state=42)
        clf.fit(X_train, y_train)
        preds = clf.predict(X_test)
        acc = float(accuracy_score(y_test, preds))
        all_acc.append(acc)
        ts = int(time.time())
        fname = MODEL_DIR / f"rf_model_{ts}.pkl"
        with fname.open("wb") as f:
            pickle.dump({"model": clf, "meta": {"source_csv": p, "acc": acc, "created_at": ts}}, f)
        models.append(str(fname))
    return {"models": models, "accuracies": all_acc}
