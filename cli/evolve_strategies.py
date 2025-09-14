from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict

import numpy as np
import pandas as pd

from research.evolution.ga_trader import run_ga, StrategyGenome


def _load_prices(path: str | None) -> pd.DataFrame:
    if path and os.path.exists(path):
        df = pd.read_csv(path)
        if "time" in df.columns:
            df = df.set_index("time")
        return df
    # synthetic
    rng = np.random.default_rng(0)
    cols = [f"A{i}" for i in range(8)]
    data = {}
    for i, c in enumerate(cols):
        steps = rng.normal(0.0005 - 0.0002 * (i % 3), 0.01, size=400)
        data[c] = 100 * np.cumprod(1.0 + steps)
    idx = pd.date_range(end=pd.Timestamp.utcnow().floor("min"), periods=400, freq="1min")
    return pd.DataFrame(data, index=idx)


def main():
    p = argparse.ArgumentParser(description="Evolve strategies (GA)")
    p.add_argument("--csv", default=None)
    p.add_argument("--pop", type=int, default=30)
    p.add_argument("--gens", type=int, default=20)
    p.add_argument("--seed", type=int, default=123)
    p.add_argument("--top", type=int, default=5)
    args = p.parse_args()

    df = _load_prices(args.csv)
    best, leaderboard = run_ga(df, pop=args.pop, gens=args.gens, seed=args.seed)
    # Optionally persist best genome
    try:
        os.makedirs("storage", exist_ok=True)
        with open(os.path.join("storage", "strategies.json"), "w", encoding="utf-8") as f:
            json.dump({"best": best.__dict__, "leaderboard": leaderboard}, f, indent=2)
    except Exception:
        pass
    print(json.dumps({"best": best.__dict__, "leaderboard": leaderboard}))


if __name__ == "__main__":
    main()

