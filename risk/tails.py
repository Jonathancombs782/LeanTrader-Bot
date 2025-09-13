from __future__ import annotations

from typing import Tuple, Dict, Any

import numpy as np


def classical_var_cvar(pnl_series: np.ndarray, alpha: float = 0.95) -> Tuple[float, float]:
    """Compute one-sided VaR and CVaR (Expected Shortfall) from a PnL series.

    VaR/CVaR are reported as positive loss magnitudes. We use the lower tail
    of the PnL distribution at level (1 - alpha).
    """
    x = np.asarray(pnl_series, dtype=float).reshape(-1)
    if x.size == 0:
        return 0.0, 0.0
    # lower quantile of PnL; losses are negative PnL
    q = float(np.quantile(x, 1.0 - float(alpha)))
    var = float(max(0.0, -q))
    tail = x[x <= q]
    cvar = float(max(0.0, -np.mean(tail))) if tail.size > 0 else var
    return var, cvar


def quantum_tail_estimator(
    returns_vec: np.ndarray,
    cov_matrix: np.ndarray,
    alpha: float = 0.95,
    use_runtime: bool = True,
    samples: int = 100_000,
) -> Dict[str, Any]:
    """Quantum-aware tail estimator (Monte Carlo fallback).

    For now this uses classical Monte Carlo simulation of portfolio returns:
      - Equal-weight portfolio w = 1/N
      - Draw samples from N(mu, Sigma)
      - Estimate VaR/CVaR on the simulated distribution

    TODO: Replace with Quantum Amplitude Estimation (QAE) based credit-risk
    or tail circuits leveraging Qiskit (Runtime when use_runtime=True).
    """
    mu = np.asarray(returns_vec, dtype=float).reshape(-1)
    Sigma = np.asarray(cov_matrix, dtype=float)
    n = mu.shape[0]
    if Sigma.shape != (n, n):
        Sigma = np.diag(np.ones(n, dtype=float))

    # Equal weights portfolio
    w = np.ones(n, dtype=float) / max(1, n)

    # Classical MC fallback
    rng = np.random.default_rng(42)
    try:
        draws = rng.multivariate_normal(mean=mu, cov=Sigma, size=int(samples))
        port = draws @ w
    except Exception:
        # If covariance not PD, add jitter on diagonal
        jitter = 1e-8 * np.eye(n)
        draws = rng.multivariate_normal(mean=mu, cov=Sigma + jitter, size=int(samples))
        port = draws @ w

    var, cvar = classical_var_cvar(port, alpha=alpha)
    return {
        "alpha": float(alpha),
        "var": float(var),
        "cvar": float(cvar),
        "samples": int(samples),
        "method": "mc_fallback",
        "use_runtime": bool(use_runtime),
    }

