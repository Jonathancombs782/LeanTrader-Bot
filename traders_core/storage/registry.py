from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Tuple  # noqa: F401  # intentionally kept

import joblib


def _dir(base: str, *parts) -> Path:
    p = Path(base).joinpath(*parts)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_model(symbol: str, timeframe: str, model: Any, meta: dict, models_dir: str) -> str:
    ts = int(time.time())
    mid = f"{symbol}_{timeframe}_{ts}"
    d = _dir(models_dir, symbol, timeframe, mid)
    joblib.dump(model, d / "model.joblib")
    (d / "meta.json").write_text(json.dumps(meta, indent=2))
    return mid


def load_latest(symbol: str, timeframe: str, models_dir: str):
    root = Path(models_dir) / symbol / timeframe
    if not root.exists():
        return None, None
    mids = sorted(os.listdir(root))
    if not mids:
        return None, None
    last = root / mids[-1]
    return joblib.load(last / "model.joblib"), json.loads((last / "meta.json").read_text())


# ADD these helpers under existing code


def save_model_tagged(symbol: str, timeframe: str, tag: str, model: Any, meta: dict, models_dir: str) -> str:
    # saves under .../<symbol>/<timeframe>/<tag>/<ts>/
    import json
    import time
    from pathlib import Path  # noqa: F401  # intentionally kept

    import joblib

    ts = int(time.time())
    d = _dir(models_dir, symbol, timeframe, tag, str(ts))
    joblib.dump(model, d / "model.joblib")
    (d / "meta.json").write_text(json.dumps({**meta, "tag": tag}, indent=2))
    return f"{symbol}_{timeframe}_{tag}_{ts}"


def load_latest_tagged(symbol: str, timeframe: str, tag: str, models_dir: str):
    root = Path(models_dir) / symbol / timeframe / tag
    if not root.exists():
        return None, None
    mids = sorted(os.listdir(root))
    if not mids:
        return None, None
    last = root / mids[-1]
    import json

    import joblib

    return joblib.load(last / "model.joblib"), json.loads((last / "meta.json").read_text())
