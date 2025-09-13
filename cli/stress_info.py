from __future__ import annotations

import argparse
import json
import os

import numpy as np
import pandas as pd

from features.pipeline import compute_mu_cov
from risk.adaptive_budget import stress_indicator, adaptive_budget


def _load_prices(path: str | None) -> pd.DataFrame:
    if path and os.path.exists(path):
        df = pd.read_csv(path)
        if "time" in df.columns:
            df = df.set_index("time")
        return df
    # synthetic
    rng = np.random.default_rng(0)
    cols = [f"A{i}" for i in range(6)]
    data = {}
    for i, c in enumerate(cols):
        steps = rng.normal(0.0005 - 0.0002 * (i % 2), 0.01, size=300)
        data[c] = 100 * np.cumprod(1.0 + steps)
    idx = pd.date_range(end=pd.Timestamp.utcnow().floor("min"), periods=300, freq="1min")
    return pd.DataFrame(data, index=idx)


def main():
    p = argparse.ArgumentParser(description="Compute stress indicator and suggested leverage")
    p.add_argument("--csv", default=None)
    p.add_argument("--window", type=int, default=252)
    args = p.parse_args()

    df = _load_prices(args.csv)
    mu, Sigma = compute_mu_cov(df, window=args.window)
    vol_proxy = float(np.sqrt(np.mean(np.clip(np.diag(Sigma), 1e-12, None)))) if Sigma.size else 0.0
    vix_proxy = float(os.getenv("VIX_PROXY", "20"))
    liq_proxy = 1.0
    s = stress_indicator(vol_proxy, vix_proxy, liq_proxy)
    w_base = np.ones(mu.shape[0]) / max(1, mu.shape[0]) if mu.size else np.array([1.0])
    w, L = adaptive_budget(w_base, s)
    print(json.dumps({"stress_s": s, "leverage_L": L}))


if __name__ == "__main__":
    main()

