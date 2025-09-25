from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

from web3.guards import (
    estimate_price_impact,
    is_safe_price_impact,
    is_safe_gas,
    token_safety_checks,
    mempool_monitor,
    dynamic_slippage,
    private_tx_mode,
)


class GuardError(Exception):
    pass


# Hooks to integrate with real DEX router; these should be replaced in your app
def _get_reserves(pair) -> Tuple[float, float]:  # reserves_in, reserves_out
    raise NotImplementedError("_get_reserves must be implemented in your integration")


def _get_current_gas_gwei() -> float:
    raise NotImplementedError("_get_current_gas_gwei must be implemented in your integration")


def _get_token_meta(pair) -> Dict[str, Any]:
    return {}


def _router_swap(pair, amount_in, wallet, slippage_bps=50) -> Dict[str, Any]:
    raise NotImplementedError("_router_swap must be implemented in your integration")


def _router_swap_private(pair, amount_in, wallet, slippage_bps=50) -> Dict[str, Any]:
    """Private tx route (Flashbots/MEV-Share) hook."""
    raise NotImplementedError("_router_swap_private must be implemented in your integration")


def guarded_swap(
    pair,
    amount_in,
    wallet,
    slippage_bps: int = 50,
    max_price_impact: int = 100,
    max_fee_gwei: float = 100.0,
) -> Dict[str, Any]:
    """Perform a guarded swap via original router.

    - max_price_impact in bps (e.g., 100 = 1%)
    - max_fee_gwei threshold for current basefee
    """
    try:
        rin, rout = _get_reserves(pair)
    except Exception as e:
        raise GuardError(f"reserves_unavailable:{e}")
    impact = estimate_price_impact(float(amount_in), float(rin), float(rout))
    if not is_safe_price_impact(impact, max_impact=float(max_price_impact) / 1e4):
        raise GuardError(f"price_impact_exceeded:{impact:.6f}>{float(max_price_impact)/1e4:.6f}")

    try:
        gas = float(_get_current_gas_gwei())
    except Exception as e:
        raise GuardError(f"gas_unavailable:{e}")
    if not is_safe_gas(float(max_fee_gwei), gas):
        raise GuardError(f"gas_too_high:{gas:.2f}>{float(max_fee_gwei):.2f}")

    meta = {}
    try:
        meta = _get_token_meta(pair) or {}
    except Exception:
        meta = {}
    sec = token_safety_checks(meta)
    if not sec.get("ok", False):
        raise GuardError("token_safety_failed:" + ",".join(sec.get("reasons", [])))

    # Mempool risk & slippage adjustment
    risk_sub = meta.get("mempool") if isinstance(meta, dict) else None
    risk = mempool_monitor(risk_sub)
    try:
        from observability.metrics import set_mempool_risk
        set_mempool_risk(risk)
    except Exception:
        pass
    adj_slip = dynamic_slippage(int(slippage_bps), risk)

    # Consider private route on high risk or large amount
    use_private = private_tx_mode(float(meta.get("amount_usd", amount_in)), risk)
    try:
        if use_private:
            return _router_swap_private(pair, amount_in, wallet, slippage_bps=adj_slip)
        return _router_swap(pair, amount_in, wallet, slippage_bps=adj_slip)
    except Exception as e:
        raise GuardError(f"swap_reverted:{e}")


__all__ = ["GuardError", "guarded_swap"]
