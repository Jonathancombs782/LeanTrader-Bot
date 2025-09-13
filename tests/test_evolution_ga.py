from __future__ import annotations

import numpy as np
import pandas as pd

from research.evolution.ga_trader import run_ga


def _make_prices(n=300, m=6, seed=0):
    rng = np.random.default_rng(seed)
    data = {}
    for i in range(m):
        steps = rng.normal(0.0004 - 0.0001 * (i % 2), 0.01, size=n)
        data[f"A{i}"] = 100 * np.cumprod(1.0 + steps)
    idx = pd.date_range(end=pd.Timestamp.utcnow().floor("min"), periods=n, freq="1min")
    return pd.DataFrame(data, index=idx)


def test_ga_determinism_and_progress():
    df = _make_prices()
    best1, lb1 = run_ga(df, pop=10, gens=5, seed=42)
    best2, lb2 = run_ga(df, pop=10, gens=5, seed=42)
    assert best1.__dict__ == best2.__dict__
    # Progress: best_sharpe in final gen >= first gen
    assert lb1[-1]["best_sharpe"] >= lb1[0]["best_sharpe"] - 1e-9

