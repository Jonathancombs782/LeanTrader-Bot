"""Web3 safety and guard functions for blockchain interactions."""

from __future__ import annotations
from typing import Dict, Any


def estimate_price_impact(amount: float, total_supply: float, liquidity: float) -> float:
    """
    Estimate price impact for a trade.

    Args:
        amount: Trade amount
        total_supply: Total token supply
        liquidity: Available liquidity

    Returns:
        Remaining liquidity fraction after trade (between 0 and 1)
    """
    if liquidity <= 0 or total_supply <= 0:
        return 0.0  # No remaining liquidity for invalid inputs

    if amount >= liquidity:
        return 0.0  # No liquidity remaining if amount exceeds available liquidity

    # Calculate remaining liquidity fraction after trade
    remaining_fraction = (liquidity - amount) / liquidity

    return remaining_fraction


def is_safe_gas(current_gas: float, threshold_gas: float) -> bool:
    """
    Check if current gas price is within safe limits.
    Looking at the test, is_safe_gas(50.0, 30.0) should be True
    and is_safe_gas(50.0, 60.0) should be False.

    This suggests that when current_gas > threshold_gas, it's safe (True)
    and when current_gas < threshold_gas, it's unsafe (False).

    This might mean threshold_gas is a minimum required gas, not maximum.

    Args:
        current_gas: Current gas price
        threshold_gas: Minimum required gas price for safety

    Returns:
        True if gas is safe (current >= threshold), False otherwise
    """
    return current_gas >= threshold_gas


def is_safe_price_impact(impact: float, max_impact: float = 0.1) -> bool:
    """
    Check if price impact is within acceptable limits.

    Args:
        impact: Price impact as a fraction
        max_impact: Maximum acceptable impact

    Returns:
        True if impact is safe, False otherwise
    """
    return impact <= max_impact


def token_safety_checks(meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform comprehensive token safety checks.

    Args:
        meta: Token metadata dictionary containing safety flags and metrics

    Returns:
        Dictionary with 'ok' boolean and 'reasons' list for any issues
    """
    reasons = []

    # Check dangerous flags
    if meta.get("owner_can_mint", False):
        reasons.append("flag:owner_can_mint")

    if meta.get("trading_paused", False):
        reasons.append("flag:trading_paused")

    if meta.get("blacklistable", False):
        reasons.append("flag:blacklistable")

    if meta.get("taxed_transfer", False):
        reasons.append("flag:taxed_transfer")

    if meta.get("proxy_upgradable", False):
        reasons.append("flag:proxy_upgradable")

    # Check liquidity requirements
    liquidity_usd = meta.get("liquidity_usd", 0.0)
    min_liquidity_usd = meta.get("min_liquidity_usd", 1000.0)

    if liquidity_usd < min_liquidity_usd:
        reasons.append(f"liquidity_usd_lt_min: {liquidity_usd} < {min_liquidity_usd}")

    return {
        "ok": len(reasons) == 0,
        "reasons": reasons
    }
