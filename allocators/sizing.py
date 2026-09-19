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

    Each overweight sector is scaled down to exactly ``sector_cap`` and then
    pinned; the remaining (unpinned) assets are rescaled so the total returns
    to 1 without touching the pinned sectors. Pinning is what makes this
    converge: the previous implementation renormalized *all* assets together,
    which re-inflated capped sectors above the cap every iteration and could
    never satisfy the cap. If the caps are infeasible (sum of caps < 1) the
    result is best-effort.
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
    in_sector = {i for idxs in sectors.values() for i in idxs}

    pinned = set()
    for _ in range(len(sectors) + 1):
        # Scale every overweight sector down to exactly the cap and pin it.
        for s, idxs in sectors.items():
            if s in pinned:
                continue
            ssum = float(np.sum(out[idxs]))
            if ssum > sector_cap + 1e-12 and ssum > 0:
                out[idxs] *= sector_cap / ssum
                pinned.add(s)
        # Restore the total to 1 using only unpinned assets, so pinned
        # sectors stay exactly at the cap.
        free = [i for s, idxs in sectors.items() if s not in pinned for i in idxs]
        free += [i for i in range(out.shape[0]) if i not in in_sector]
        if not free:
            break
        pinned_sum = float(np.sum([out[i] for i in range(out.shape[0]) if i not in free]))
        free_sum = float(np.sum(out[free]))
        if free_sum > 1e-15 and pinned_sum < 1.0:
            out[free] *= (1.0 - pinned_sum) / free_sum
        # Converged when no unpinned sector is overweight.
        ok = True
        for s, idxs in sectors.items():
            if s not in pinned and float(np.sum(out[idxs])) > sector_cap + 1e-9:
                ok = False
                break
        if ok:
            break
    return _l1_normalize(out)


__all__ = ["vol_scaled_weights", "apply_exposure_caps"]

