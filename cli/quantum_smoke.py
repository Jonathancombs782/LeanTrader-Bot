try:
    import click
except Exception:
    click = None  # fallback to argparse in __main__

import os
import numpy as np
import pandas as pd

from features.pipeline import compute_mu_cov
from allocators.portfolio import choose_assets


def _load_prices(path: str | None, n: int = 300, cols: int = 8) -> pd.DataFrame:
    if path and os.path.exists(path):
        df = pd.read_csv(path)
        # try to parse time index if present
        try:
            if "time" in df.columns:
                df = df.set_index("time")
        except Exception:
            pass
        return df
    # synthetic
    rng = np.random.default_rng(0)
    data = {}
    for i in range(cols):
        steps = rng.normal(0.0005 - 0.0002 * (i % 3), 0.01, size=n)
        data[f"A{i}"] = 100 * np.cumprod(1.0 + steps)
    idx = pd.date_range(end=pd.Timestamp.utcnow().floor("min"), periods=n, freq="1min")
    return pd.DataFrame(data, index=idx)


def _run(path: str | None, budget: int, window: int, regime: str | None, quantum: bool):
    os.environ["Q_ENABLE_QUANTUM"] = "true" if quantum else "false"
    df = _load_prices(path)
    mu, Sigma = compute_mu_cov(df, window=window)
    x = choose_assets(mu, Sigma, budget=budget)
    sel_idx = list(np.where(x == 1)[0])
    print({
        "regime": regime,
        "q_enabled": quantum,
        "selected_count": int(x.sum()),
        "selected_indices": sel_idx,
    })


if click:

    @click.command()
    @click.argument("data_csv", required=False)
    @click.option("--budget", default=5, type=int)
    @click.option("--window", default=252, type=int)
    @click.option("--regime", default="calm", type=str)
    @click.option("--quantum/--no-quantum", default=False)
    def main(data_csv, budget, window, regime, quantum):
        _run(data_csv, budget, window, regime, quantum)

else:
    def main():  # argparse fallback
        import argparse

        p = argparse.ArgumentParser()
        p.add_argument("data_csv", nargs="?")
        p.add_argument("--budget", type=int, default=5)
        p.add_argument("--window", type=int, default=252)
        p.add_argument("--regime", type=str, default="calm")
        p.add_argument("--quantum", action="store_true")
        args = p.parse_args()
        _run(args.data_csv, args.budget, args.window, args.regime, args.quantum)


if __name__ == "__main__":
    main()

