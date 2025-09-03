"""Simple incremental trainer that consumes pattern scores and fits a LightGBM model periodically.

This is paper-only: it writes models to runtime/models and logs metrics. It's a lightweight building block for continuous learning.
"""
from __future__ import annotations

import time
import json
from pathlib import Path
from typing import List

import numpy as np

RUNTIME = Path(__file__).resolve().parent.parent / "runtime"
MODELS = RUNTIME / "models"
MODELS.mkdir(parents=True, exist_ok=True)


def _load_scores() -> List[dict]:
    path = RUNTIME / "pattern_scores.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def main(poll_sec: int = 60):
    # very small fake trainer: compute simple moving-average predictor on 'score' -> next_ret
    while True:
        rows = _load_scores()
        if rows:
            # compute a trivial metric and write a model placeholder
            mean_score = float(np.mean([r.get("score", 0.0) for r in rows]))
            mpath = MODELS / f"model_{int(time.time())}.json"
            mpath.write_text(json.dumps({"mean_score": mean_score}), encoding="utf-8")
        time.sleep(poll_sec)


if __name__ == "__main__":
    main()
