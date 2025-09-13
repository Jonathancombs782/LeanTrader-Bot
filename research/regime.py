"""Regime-aware quantum gating helpers.

Provides small utilities to decide whether quantum routines should be enabled
for a given market regime.
"""

from __future__ import annotations

from typing import Optional, Set

try:
    from config import Q_ENABLE_QUANTUM  # default flag from environment
except Exception:
    Q_ENABLE_QUANTUM = False  # sensible default if config is unavailable


# Allowlist of regimes where quantum search/estimation is likely helpful.
QUANTUM_OK: Set[str] = {"range_bound", "low_vol_trend", "calm"}


def quantum_allowed_for_regime(regime: Optional[str]) -> bool:
    """Return True if regime is in the approved set for quantum routines.

    Unknown or None regimes return False.
    """
    if not regime:
        return False
    try:
        return str(regime).strip().lower() in QUANTUM_OK
    except Exception:
        return False


def select_quantum_mode(regime: Optional[str], default_on: bool) -> bool:
    """Combine config and regime gate to decide quantum enablement.

    Returns True only if:
      - Global env flag (Q_ENABLE_QUANTUM) is True, AND
      - The provided regime is allowed, AND
      - default_on is True (caller-provided preference)
    Unknown/None regime yields False.
    """
    if not quantum_allowed_for_regime(regime):
        return False
    try:
        return bool(Q_ENABLE_QUANTUM) and bool(default_on)
    except Exception:
        return False


__all__ = [
    "QUANTUM_OK",
    "quantum_allowed_for_regime",
    "select_quantum_mode",
]

