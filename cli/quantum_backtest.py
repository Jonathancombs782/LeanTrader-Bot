"""CLI wrapper for research.backtest.quantum_ab.run_ab_backtest.

Usage:
  python -m cli.quantum_backtest --csv data.csv --budget 10 --window 252 --seed 123
Prints a single-line JSON result and exits 0 on success, 1 on error.
"""

from __future__ import annotations

import json
import os
import sys

import pandas as pd

from research.backtest.quantum_ab import run_ab_backtest
try:
    from risk.tails import classical_var_cvar
except Exception:
    def classical_var_cvar(x, alpha=0.95):
        return 0.0, 0.0


def main():
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--csv", dest="csv", default=None)
    p.add_argument("--budget", type=int, default=10)
    p.add_argument("--window", type=int, default=252)
    p.add_argument("--seed", type=int, default=123)
    args = p.parse_args()

    try:
        if args.csv and os.path.exists(args.csv):
            df = pd.read_csv(args.csv)
            if "time" in df.columns:
                df = df.set_index("time")
        else:
            # synthetic fallback
            from numpy.random import default_rng
            import numpy as np
            rng = default_rng(args.seed)
            cols = [f"A{i}" for i in range(6)]
            data = {}
            for i, c in enumerate(cols):
                steps = rng.normal(0.0004 - 0.0001 * (i % 3), 0.01, size=320)
                data[c] = 100 * np.cumprod(1.0 + steps)
            idx = pd.date_range(end=pd.Timestamp.utcnow().floor("min"), periods=320, freq="1min")
            df = pd.DataFrame(data, index=idx)
        res = run_ab_backtest(df, budget=args.budget, window=args.window, seed=args.seed)
        # augment with VaR/CVaR for each track
        try:
            pnl_c = res.get("classical", {}).get("pnl_series", [])
            pnl_q = res.get("quantum", {}).get("pnl_series", [])
            var_c, cvar_c = classical_var_cvar(np.asarray(pnl_c, dtype=float), alpha=0.95)
            var_q, cvar_q = classical_var_cvar(np.asarray(pnl_q, dtype=float), alpha=0.95)
            res["risk"] = {
                "classical": {"var": float(var_c), "cvar": float(cvar_c)},
                "quantum": {"var": float(var_q), "cvar": float(cvar_q)},
            }
        except Exception:
            pass
        print(json.dumps(res))
        sys.exit(0)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
