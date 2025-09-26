from __future__ import annotations

from typing import Optional, Tuple

import numpy as np


def _l1_normalize(w: np.ndarray) -> np.ndarray:
    s = float(np.sum(np.abs(w)))
    return (w / s) if s > 0 else w * 0.0


def compute_risk_parity_weights(Sigma: np.ndarray, mask: Optional[np.ndarray] = None, iters: int = 200) -> np.ndarray:
    """Iterative risk parity weights for selected assets.

    Uses simple fixed-point iteration on risk contributions:
      w <- w * (target_rc / rc), normalized to sum 1.
    """
    Sig = np.asarray(Sigma, dtype=float)
    n = Sig.shape[0]
    if Sig.ndim != 2 or Sig.shape[0] != Sig.shape[1]:
        return np.ones(n) / n
    if mask is None:
        m = np.ones(n, dtype=float)
    else:
        m = np.asarray(mask, dtype=float).reshape(-1)
        if m.shape[0] != n:
            m = np.ones(n, dtype=float)
    # initialize
    diag = np.clip(np.diag(Sig), 1e-8, None)
    w = m * (1.0 / np.sqrt(diag))
    if np.sum(w) <= 0:
        w = m.copy()
    w = _l1_normalize(w)
    # target equal risk among selected
    k = max(1, int(np.sum(m > 0.5)))
    for _ in range(max(1, int(iters))):
        # risk contributions
        rc = w * (Sig @ w)
        total = float(np.sum(rc))
        if total <= 1e-12:
            break
        target = total / float(k)
        # avoid division by zero
        adj = np.where(rc > 1e-12, target / rc, 1.0)
        # mask: freeze zeros
        w = np.where(m > 0.5, w * adj, 0.0)
        w = _l1_normalize(w)
    return w


def stress_indicator(vol: float, vix_proxy: float, liquidity: float) -> float:
    """Combine volatility, VIX-like proxy, and liquidity into stress score [0,1].

    Higher vol and VIX increase stress; higher liquidity reduces it.
    """
    try:
        vol_n = max(0.0, min(1.0, float(vol) / 0.3))  # 30% annual vol as 1.0 benchmark
    except Exception:
        vol_n = 0.0
    try:
        vix_n = max(0.0, min(1.0, float(vix_proxy) / 40.0))  # 40 VIX ~ 1.0
    except Exception:
        vix_n = 0.0
    try:
        liq_n = max(0.0, min(1.0, 1.0 / max(1e-6, float(liquidity))))  # more liq => smaller liq_n
    except Exception:
        liq_n = 0.5
    # weights: vol 0.5, vix 0.4, liq 0.1 (inverse)
    s = 0.5 * vol_n + 0.4 * vix_n + 0.1 * liq_n
    return float(max(0.0, min(1.0, s)))


def adaptive_budget(w_base: np.ndarray, stress_s: float, min_leverage: float = 0.5, max_leverage: float = 1.5) -> Tuple[np.ndarray, float]:
    """Scale portfolio weights by leverage L that decays with stress, then renormalize.

    Returns (weights, L)."""
    try:
        s = float(max(0.0, min(1.0, stress_s)))
        L = float(max_leverage + (min_leverage - max_leverage) * s)  # lerp
    except Exception:
        L = 1.0
    w = np.asarray(w_base, dtype=float).reshape(-1)
    w_scaled = _l1_normalize(L * w)
    return w_scaled, L


__all__ = [
    "compute_risk_parity_weights",
    "stress_indicator",
    "adaptive_budget",
]

