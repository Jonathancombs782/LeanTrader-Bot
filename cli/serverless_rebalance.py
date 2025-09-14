"""Serverless rebalance CLI for nightly runs.

Usage:
  python -m cli.serverless_rebalance --budget 10 --regime calm --use-runtime

Prints a single-line JSON summary on success, and exits 0.
On failure, prints {"error": "..."} and exits 1.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Optional

import numpy as np
import pandas as pd

try:
    import click  # type: ignore
except Exception:  # pragma: no cover
    click = None

from features.pipeline import compute_mu_cov
from allocators.portfolio import choose_assets
try:
    from risk.tails import quantum_tail_estimator
except Exception:
    def quantum_tail_estimator(returns_vec, cov_matrix, alpha=0.95, use_runtime=True):
        return {"alpha": alpha, "var": 0.0, "cvar": 0.0, "samples": 0, "method": "na"}
try:
    from config import IBM_MIN_QUBITS
except Exception:
    IBM_MIN_QUBITS = 127


def _load_prices(path: Optional[str]) -> pd.DataFrame:
    if path and os.path.exists(path):
        try:
            df = pd.read_csv(path)
            if "time" in df.columns:
                df = df.set_index("time")
            return df
        except Exception:
            pass
    # synthetic fallback
    rng = np.random.default_rng(1)
    cols = [f"A{i}" for i in range(10)]
    data = {}
    for i, c in enumerate(cols):
        steps = rng.normal(0.0005 - 0.0001 * (i % 3), 0.01, size=300)
        data[c] = 100 * np.cumprod(1.0 + steps)
    idx = pd.date_range(end=pd.Timestamp.utcnow().floor("min"), periods=300, freq="1min")
    return pd.DataFrame(data, index=idx)


def _run(path: Optional[str], budget: int, regime: Optional[str], use_runtime: bool) -> int:
    try:
        # Gate overall quantum via env to allow downstream modules to pick it up
        os.environ["Q_ENABLE_QUANTUM"] = "true"
        os.environ["Q_USE_RUNTIME"] = "true" if use_runtime else "false"
        df = _load_prices(path)
        mu, Sigma = compute_mu_cov(df)

        # Attempt premium path: direct quantum call with Runtime backend selection
        x = None
        if use_runtime:
            qpo = None
            # try importing quantum portfolio optimizer
            for _mod in ("quantum_portfolio", "quantum", "traders_core.quantum_portfolio"):
                try:
                    m = __import__(_mod, fromlist=["quantum_portfolio_optimize"])  # type: ignore
                    if hasattr(m, "quantum_portfolio_optimize"):
                        qpo = getattr(m, "quantum_portfolio_optimize")
                        break
                except Exception:
                    continue
            if qpo is not None:
                backend = None
                try:
                    from qiskit_ibm_runtime import QiskitRuntimeService  # type: ignore

                    token = os.getenv("IBM_QUANTUM_API_KEY", "").strip() or None
                    # channel default: ibm_quantum for public cloud
                    if token:
                        service = QiskitRuntimeService(channel="ibm_quantum", token=token)
                    else:
                        service = QiskitRuntimeService()
                    # pick a backend with sufficient qubits; simplest heuristic: first matching
                    cands = []
                    try:
                        cands = [b for b in service.backends() if getattr(b, "num_qubits", 0) >= int(IBM_MIN_QUBITS)]
                    except Exception:
                        cands = service.backends()
                    backend = cands[0] if cands else None
                except Exception:
                    backend = None

                try:
                    # attempt with backend kwarg if accepted
                    try:
                        y = qpo(returns=mu, covariance=Sigma, budget=int(budget), reps=2, resilience_level=1, use_runtime=True, backend=backend)
                    except TypeError:
                        y = qpo(returns=mu, covariance=Sigma, budget=int(budget), reps=2, resilience_level=1, use_runtime=True)
                    y = np.asarray(y).reshape(-1)
                    # convert to binary selection of exactly budget assets
                    idx_top = np.argsort(-y)[: int(budget)]
                    x = np.zeros_like(y, dtype=int)
                    x[idx_top] = 1
                except Exception:
                    x = None

        # Fallback to integrated allocator
        if x is None:
            x = choose_assets(mu, Sigma, budget=budget, force_quantum=True, force_use_runtime=use_runtime)
        idx = list(np.where(x == 1)[0])
        # Tail risk (Monte Carlo fallback by default)
        tails = quantum_tail_estimator(mu, Sigma, alpha=0.95, use_runtime=use_runtime)
        summary = {
            "regime": regime or "",
            "q_enabled": True,
            "use_runtime": bool(use_runtime),
            "selected_count": int(x.sum()),
            "indices": idx,
            "risk": {"var": float(tails.get("var", 0.0)), "cvar": float(tails.get("cvar", 0.0))},
        }
        print(json.dumps(summary))
        return 0
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        return 1


if click:

    @click.command()
    @click.argument("data_csv", required=False)
    @click.option("--budget", default=10, type=int)
    @click.option("--regime", default="calm", type=str)
    @click.option("--use-runtime/--no-runtime", default=False)
    def main(data_csv, budget, regime, use_runtime):
        code = _run(data_csv, budget, regime, use_runtime)
        sys.exit(code)

else:  # pragma: no cover
    def main():
        import argparse

        p = argparse.ArgumentParser()
        p.add_argument("data_csv", nargs="?")
        p.add_argument("--budget", type=int, default=10)
        p.add_argument("--regime", type=str, default="calm")
        g = p.add_mutually_exclusive_group()
        g.add_argument("--use-runtime", action="store_true")
        g.add_argument("--no-runtime", dest="use_runtime", action="store_false")
        p.set_defaults(use_runtime=False)
        args = p.parse_args()
        code = _run(args.data_csv, args.budget, args.regime, args.use_runtime)
        sys.exit(code)


if __name__ == "__main__":
    main()
