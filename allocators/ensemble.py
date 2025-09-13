from __future__ import annotations

from typing import Optional

import numpy as np
try:
    from observability.metrics import record_ensemble_lambda
except Exception:  # pragma: no cover
    def record_ensemble_lambda(val: float):
        return None
try:
    from observability.metrics import ENSEMBLE_LAMBDA_CAP_G, record_ensemble_lambda_cap
except Exception:  # pragma: no cover
    ENSEMBLE_LAMBDA_CAP_G = None  # type: ignore
    def record_ensemble_lambda_cap(val: float):
        return None
try:
    from ops.auto_throttle import get_lambda_cap
except Exception:  # pragma: no cover
    def get_lambda_cap(default=None):
        return default


def blend_weights(w_q: np.ndarray, w_c: np.ndarray, lam: float = 0.5, norm: bool = True) -> np.ndarray:
    """Linear blend of quantum and classical weights.

    w = lam * w_q + (1 - lam) * w_c
    If norm is True, renormalize L1 to 1 (preserve sign if shorting allowed).
    """
    a = np.asarray(w_q, dtype=float).reshape(-1)
    b = np.asarray(w_c, dtype=float).reshape(-1)
    n = max(a.shape[0], b.shape[0])
    if a.shape[0] != n:
        a = np.resize(a, n)
    if b.shape[0] != n:
        b = np.resize(b, n)
    w = float(lam) * a + (1.0 - float(lam)) * b
    if norm:
        s = float(np.sum(np.abs(w)))
        if s > 0:
            w = w / s
    return w


def regime_weight_lambda(regime: Optional[str]) -> float:
    """Return blending lambda based on regime.

    Higher lambda for calm/low_vol trends (favor quantum), lower for high vol.
    """
    if not regime:
        lam = 0.5
        record_ensemble_lambda(lam)
        return lam
    r = str(regime).strip().lower()
    if r in ("calm", "low_vol_trend", "range_bound"):
        lam = 0.7
    elif r in ("storm", "high_vol", "spike"):
        lam = 0.3
    else:
        lam = 0.5
    try:
        record_ensemble_lambda(lam)
    except Exception:
        pass
    # Apply optional ops cap
    try:
        cap = get_lambda_cap(None)
        if cap is not None:
            lam = min(lam, float(cap))
            try:
                record_ensemble_lambda_cap(lam)
            except Exception:
                pass
    except Exception:
        pass
    return lam


__all__ = ["blend_weights", "regime_weight_lambda"]
