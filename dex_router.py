from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from w3guard.guards import MempoolMonitor, PrivateTxClient, get_mempool_tuning
from router_safe import guarded_swap


def _monitor_from_risk_json(path: str, symbol: str, timeframe: str) -> MempoolMonitor:
    import json
    from pathlib import Path

    tune = get_mempool_tuning(symbol, timeframe)
    mon = MempoolMonitor(symbol=symbol, timeframe=timeframe, window_ms=tune["window_ms"], drop_bps=tune["drop_bps"])
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        risk = float(data.get("risk", 0.0) or 0.0)
        mon.current_risk = max(0.0, min(1.0, risk))
    except Exception:
        pass
    return mon


def execute_swap(
    *,
    asset: str,
    timeframe: str,
    notional_usd: float,
    max_slippage_bps: int,
    tx_builder: Callable[[int], Any],
    send_public: Callable[[Any], Any],
    monitor: Optional[MempoolMonitor] = None,
    private_sender: Optional[Callable[[Any], Any]] = None,
    private_client: Optional[PrivateTxClient] = None,
    hedger: Any = None,
    risk_json_path: Optional[str] = None,
) -> Dict[str, Any]:
    """DEX swap with mempool-aware protections.

    Returns dict {route, slippage_bps, risk, ok, tx_resp, hedged}.
    """
    if monitor is None and risk_json_path:
        try:
            monitor = _monitor_from_risk_json(risk_json_path, asset, timeframe)
        except Exception:
            monitor = None

    return guarded_swap(
        symbol=asset,
        timeframe=timeframe,
        notional_usd=notional_usd,
        max_slippage_bps=max_slippage_bps,
        tx_builder=tx_builder,
        send_public=send_public,
        monitor=monitor,
        send_private=private_sender,
        private_client=private_client,
        hedger=hedger,
    )


__all__ = ["execute_swap"]
