from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd


def ensure_psd(Sigma: np.ndarray, eps: float = 1e-8) -> np.ndarray:
    """Ensure covariance matrix is positive semi-definite via eigenvalue floor.

    Returns a new matrix with eigenvalues clipped at `eps`.
    """
    A = np.asarray(Sigma, dtype=float)
    if A.ndim != 2 or A.shape[0] != A.shape[1]:
        n = A.shape[0] if A.ndim > 0 else 1
        return np.eye(n, dtype=float) * eps
    try:
        vals, vecs = np.linalg.eigh((A + A.T) / 2.0)
        vals = np.maximum(vals, float(eps))
        return (vecs * vals) @ vecs.T
    except Exception:
        n = A.shape[0]
        return np.eye(n, dtype=float) * eps


def compute_mu_cov(
    df: "pd.DataFrame",
    window: int = 252,
    min_history: int = 126,
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute annualized mean returns (mu) and covariance (Sigma).

    Steps:
      1) Select assets (columns) with >= min_history non-NaN observations.
      2) Compute log returns r_t = log(P_t / P_{t-1}) per asset.
      3) Estimate mu as annualized mean over the trailing `window`.
      4) Estimate Sigma as annualized sample covariance over the same window.
      5) Reorder outputs to match the selected asset columns.
      6) Handle NaN/inf by dropping incomplete rows and clipping values.

    Regularization:
      - If n < 3 or Sigma not PSD, add 1e-6 * I and ensure PSD.

    Returns (mu, Sigma) as numpy arrays.
    """
    if df is None or getattr(df, "empty", True):
        return np.array([], dtype=float), np.zeros((0, 0), dtype=float)

    dff = df.copy()
    # 1) Asset selection by history
    counts = dff.notna().sum(axis=0)
    keep_cols = [c for c in dff.columns if counts.get(c, 0) >= int(min_history)]
    if not keep_cols:
        return np.array([], dtype=float), np.zeros((0, 0), dtype=float)

    dff = dff[keep_cols].tail(max(window + 2, min_history + 2))

    # 2) Log returns
    dff = dff.replace([np.inf, -np.inf], np.nan).dropna(how="any")
    if dff.empty:
        return np.array([], dtype=float), np.zeros((0, 0), dtype=float)

    log_prices = np.log(dff.clip(lower=1e-12))
    rets = (log_prices - log_prices.shift(1)).dropna(how="any")
    if rets.empty:
        return np.array([], dtype=float), np.zeros((0, 0), dtype=float)

    # 3) Annualized mean (assume ~252 trading periods)
    mu = rets.mean(axis=0).to_numpy(dtype=float) * float(window)
    # 4) Annualized covariance
    Sigma = rets.cov().to_numpy(dtype=float) * float(window)

    n = mu.shape[0]
    if Sigma.shape != (n, n):
        Sigma = np.diag(np.ones(n, dtype=float))

    # 6) Regularization for stability
    if n < 3:
        Sigma = Sigma + 1e-6 * np.eye(n)
    # ensure PSD
    Sigma = ensure_psd(Sigma, eps=1e-8)

    return mu.reshape(-1), Sigma


__all__ = ["compute_mu_cov", "ensure_psd"]

