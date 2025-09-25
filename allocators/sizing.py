from __future__ import annotations

from typing import Dict, Optional

import numpy as np


def _l1_normalize(w: np.ndarray) -> np.ndarray:
    s = float(np.sum(np.abs(w)))
    return (w / s) if s > 0 else w * 0.0


def vol_scaled_weights(
    mu: np.ndarray,
    Sigma: np.ndarray,
    x: np.ndarray,
    floor: float = 0.0,
    cap: float = 0.10,
    target_vol: float = 0.15,
    min_atr: float = 1e-6,
) -> np.ndarray:
    """Inverse-volatility weights on selected assets with per-asset cap.

    - x: binary selection mask (1 to include, 0 exclude)
    - floor: minimum raw weight before normalization
    - cap: per-asset cap after normalization
    - target_vol: optional target portfolio volatility (annualized units of Sigma)
    - min_atr: lower bound for diagonal vol proxy to avoid division by zero
    Returns weights summing to ~1 over selected assets; others are 0.
    """
    mu = np.asarray(mu, dtype=float).reshape(-1)
    n = mu.shape[0]
    Sig = np.asarray(Sigma, dtype=float)
    if Sig.shape != (n, n):
        Sig = np.diag(np.ones(n, dtype=float))
    sel = np.asarray(x, dtype=float).reshape(-1)
    if sel.shape[0] != n:
        sel = np.resize(sel, n)

    diag = np.clip(np.diag(Sig), min_atr**2, None)
    vol = np.sqrt(diag)
    inv = np.where(sel > 0.5, 1.0 / vol, 0.0)
    if floor > 0:
        inv = np.where(inv > 0, np.maximum(inv, floor), inv)
    w = _l1_normalize(inv)

    # Apply per-asset cap iteratively
    cap = float(max(0.0, cap))
    if cap > 0:
        for _ in range(n):
            over = w > cap
            if not np.any(over):
                break
            float(np.sum(w[over]) - np.sum(np.minimum(w[over], cap)))
            w[over] = cap
            remain = np.sum(w[~over])
            if remain > 0:
                w[~over] *= (1.0 - np.sum(w[over])) / remain
            else:
                # evenly distribute remainder to uncapped (none), keep capped
                break

    # Optional risk scaling (keep L1 normalization for allocation semantics)
    try:
        port_var = float(w @ Sig @ w)
        if port_var > 1e-12 and target_vol > 0:
            s = float(target_vol / np.sqrt(port_var))
            w = _l1_normalize(w * s)
    except Exception:
        pass
    return w


def apply_exposure_caps(
    w: np.ndarray,
    sector_map: Optional[Dict[int, str]] = None,
    sector_cap: float = 0.30,
) -> np.ndarray:
    """Cap total exposure per sector; renormalize to sum 1.

    sector_map maps index -> sector name. If None, returns w unchanged.
    """
    w = np.asarray(w, dtype=float).reshape(-1)
    if not sector_map:
        return _l1_normalize(w)
    sectors = {}
    for i, s in sector_map.items():
        if 0 <= i < w.shape[0]:
            sectors.setdefault(s, []).append(i)
    out = w.copy()
    sector_cap = float(max(0.0, min(1.0, sector_cap)))

    for _ in range(10):
        changed = False
        # Scale down overweight sectors
        for s, idxs in sectors.items():
            ssum = float(np.sum(out[idxs]))
            if ssum > sector_cap and ssum > 0:
                factor = sector_cap / ssum
                out[idxs] *= factor
                changed = True
        # Renormalize
        out = _l1_normalize(out)
        # Check again
        ok = True
        for s, idxs in sectors.items():
            if float(np.sum(out[idxs])) > sector_cap + 1e-6:
                ok = False
                break
        if ok and not changed:
            break
    return out


__all__ = ["vol_scaled_weights", "apply_exposure_caps"]

