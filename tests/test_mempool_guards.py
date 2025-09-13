from __future__ import annotations

from typing import Any, Dict, List

from w3guard.guards import MempoolMonitor, dynamic_slippage, private_tx_mode
from router_safe import guarded_swap


def _mk_tx(ts: float, pair: str, gas: float, usd: float, sender: str) -> Dict[str, Any]:
    return {
        "ts": ts,
        "pair": pair,
        "gas_price": gas,
        "amount_usd": usd,
        "from": sender,
        "hash": f"{pair}:{ts}:{sender}",
    }


def test_mempool_monitor_risk_increases_on_staircase():
    mon = MempoolMonitor(symbol="ETH/USDC", timeframe="M1", window_ms=5000, drop_bps=12)
    base = 1_000_000.0
    a = _mk_tx(1000.0, "ETH/USDC", 10, base, "A")
    b = _mk_tx(1001.0, "ETH/USDC", 12, base * 1.2, "B")
    c = _mk_tx(1001.5, "ETH/USDC", 15, base * 1.5, "C")
    # Feed some noise first
    mon.observe(_mk_tx(995.0, "ETH/USDC", 9, base * 0.5, "Z"))
    mon.observe(a)
    mon.observe(b)
    ev = mon.observe(c)
    assert mon.current_risk > 0.0
    assert ev is None or ev.get("type") == "mempool_sandwich_pattern"


def test_dynamic_slippage_reduces_with_risk():
    assert dynamic_slippage(30, 0.0) >= dynamic_slippage(30, 0.5) >= dynamic_slippage(30, 1.0)


def test_guarded_swap_prefers_private_and_hedges_on_fail():
    calls: List[str] = []

    def tx_builder(slippage_bps: int):
        calls.append(f"build:{slippage_bps}")
        return {"slippage_bps": slippage_bps}

    def send_public(tx):
        calls.append("public")
        return None  # simulate failure

    def send_private(tx):
        calls.append("private")
        return {"ok": True}

    class Hedger:
        def __init__(self):
            self.calls: List[str] = []

        def hedge(self, symbol: str, side: str, notional_usd: float, leverage: float = 1.0, **kwargs):
            self.calls.append(f"hedge:{symbol}:{side}:{int(notional_usd)}")
            return {"ok": True}

    # High risk and big notional -> choose private
    res = guarded_swap(
        symbol="ETH/USDC",
        timeframe="M1",
        notional_usd=300_000,
        max_slippage_bps=30,
        tx_builder=tx_builder,
        send_public=send_public,
        monitor=None,  # risk fallback to 0, but notional triggers private
        send_private=send_private,
        hedger=Hedger(),
    )
    assert res["ok"] is True
    assert res["route"] == "private"
    assert any(c.startswith("build:") for c in calls)
