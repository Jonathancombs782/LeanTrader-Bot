from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from w3guard.guards import (
    MEMPOOL_RISK,
    FLASH_HEDGE_COUNT,
    MempoolMonitor,
    dynamic_slippage,
    private_tx_mode,
    PrivateTxClient,
    emergency_hedge,
    get_mempool_tuning,
)


def guarded_swap(
    *,
    symbol: str,
    timeframe: str,
    notional_usd: float,
    max_slippage_bps: float,
    tx_builder: Callable[[int], Any],
    send_public: Callable[[Any], Any],
    monitor: Optional[MempoolMonitor] = None,
    private_client: Optional[PrivateTxClient] = None,
    send_private: Optional[Callable[[Any], Any]] = None,
    hedger: Any = None,
    hedge_on_fail: bool = True,
) -> Dict[str, Any]:
    """Build and submit a swap with mempool-aware slippage and private routing.

    Args:
        symbol: Trading pair symbol (e.g., "ETH/USDC").
        timeframe: Timeframe key for tuning (e.g., "M1").
        notional_usd: Approximate USD size of the swap.
        max_slippage_bps: Upper bound on slippage.
        tx_builder: Callable that accepts slippage_bps and returns a raw tx object.
        send_public: Callable that submits the tx to public mempool.
        monitor: Optional MempoolMonitor to read current risk.
        private_client: Optional PrivateTxClient instance.
        send_private: Optional explicit sender for private route; overrides private_client if provided.
        hedger: Optional futures hedger object to use in emergency hedging.
        hedge_on_fail: If True, attempt hedge when public+private routes fail.

    Returns:
        Dict with details: {route, slippage_bps, risk, ok, tx_resp, hedged}
    """

    tune = get_mempool_tuning(symbol, timeframe)
    risk = monitor.current_risk if monitor else 0.0

    try:
        MEMPOOL_RISK.labels(symbol=symbol.upper(), timeframe=timeframe.upper()).set(float(risk))
    except Exception:
        pass

    slippage_bps = dynamic_slippage(max_bps=float(max_slippage_bps), risk=risk)
    prefer_private = private_tx_mode(notional_usd=notional_usd, risk=risk)

    tx = tx_builder(slippage_bps)
    route = "public"
    tx_resp = None
    ok = False
    hedged = False

    def _try_private(x: Any) -> Optional[Any]:
        nonlocal route
        try:
            if send_private is not None:
                route = "private"
                return send_private(x)
            if private_client and private_client.available():
                route = "private"
                return private_client.send(x)
        except Exception as e:
            logging.warning("Private route failed: %s", e)
            return None
        return None

    def _try_public(x: Any) -> Optional[Any]:
        nonlocal route
        try:
            route = "public"
            return send_public(x)
        except Exception as e:
            logging.warning("Public route failed: %s", e)
            return None

    # First attempt based on preference
    if prefer_private:
        tx_resp = _try_private(tx)
        if tx_resp is None:
            # fallback to public
            tx_resp = _try_public(tx)
    else:
        tx_resp = _try_public(tx)
        # If mempool risk rises during build or public fails, try private
        if tx_resp is None and (monitor and monitor.current_risk >= 0.6 or notional_usd >= 250_000):
            tx_resp = _try_private(tx)

    ok = tx_resp is not None

    # Hedge on failure for large sizes or high risk
    if hedge_on_fail and not ok and (notional_usd >= 150_000 or risk >= 0.7):
        try:
            emergency_hedge(
                hedger=hedger,
                symbol=symbol,
                side="sell",  # default to reduce long exposure; caller can override if needed
                notional_usd=notional_usd,
                leverage=1.0,
                reason="swap_route_failed",
                extra={},
            )
            hedged = True
        except Exception as e:
            logging.warning("Emergency hedge attempt failed: %s", e)
            hedged = False

    return {
        "route": route,
        "slippage_bps": slippage_bps,
        "risk": risk,
        "ok": ok,
        "tx_resp": tx_resp,
        "hedged": hedged,
    }


__all__ = [
    "guarded_swap",
]
