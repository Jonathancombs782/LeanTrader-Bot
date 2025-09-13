"""Evaluate a saved model on a CSV of OHLCV or on synthetic data."""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import List

try:
    from .model_registry import read_meta
    from .trainer import featurize_rows, load_model
except Exception as e:
    raise SystemExit(f"dependencies missing: {e}")


def load_csv(path: str) -> List[List[float]]:
    out = []
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    with p.open("r", encoding="utf-8") as f:
        r = csv.reader(f)
        next(r, None)
        for row in r:
            try:
                out.append([int(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])])
            except Exception:
                continue
    return out


def evaluate(model_path: str, csv_path: str) -> dict:
    mdl = load_model(model_path)
    rows = load_csv(csv_path)
    X = featurize_rows(rows)
    # create labels via next-return
    y = [1 if x[0] > 0 else 0 for x in X]
    preds = list(mdl.predict(X))
    correct = sum(1 for a, b in zip(preds, y) if a == b)
    acc = float(correct) / max(1, len(y))
    meta = read_meta(Path(model_path))
    return {"model": model_path, "csv": csv_path, "accuracy": acc, "meta": meta}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: python tools/evaluate_model.py <model.pkl> <ohlcv.csv>")
        raise SystemExit(2)
    out = evaluate(sys.argv[1], sys.argv[2])
    print(out)
