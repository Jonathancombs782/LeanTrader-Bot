from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Tuple


@dataclass
class FlashCrashParams:
    window_ms: int = 5000
    drop_bps: float = 150.0
    min_depth: float = 0.0  # optional liquidity thinning threshold
    cooldown_sec: int = 600


class FlashCrashGuard:
    def __init__(self, params: FlashCrashParams | None = None):
        self.params = params or FlashCrashParams()
        self._buf: Deque[Tuple[int, float, float]] = deque()  # (ts_ms, mid, depth)
        self._cool_until: int = 0

    def update(self, mid: float, depth: float, ts_ms: int | None = None) -> bool:
        now = int(ts_ms or int(time.time() * 1000))
        # cooldown
        if now < self._cool_until:
            return False
        # append
        try:
            m = float(mid)
            d = float(depth)
        except Exception:
            return False
        self._buf.append((now, m, d))
        cutoff = now - int(self.params.window_ms)
        while self._buf and self._buf[0][0] < cutoff:
            self._buf.popleft()
        if len(self._buf) < 2:
            return False
        # compute drop from max mid in window
        highs = max(x[1] for x in self._buf)
        drop = (highs - m) / max(1e-12, highs) * 1e4
        if drop >= float(self.params.drop_bps):
            # optional depth thinning: current depth less than 50% of median depth
            try:
                med_depth = sorted(x[2] for x in self._buf)[len(self._buf) // 2]
                if med_depth > 0 and (d / med_depth) > 0.5 and self.params.min_depth > 0:
                    return False
            except Exception:
                pass
            # trip
            self._cool_until = now + int(self.params.cooldown_sec * 1000)
            return True
        return False


def emergency_hedge(exposure_usd: float, futures_venue: str, max_slippage_bps: float = 50.0, symbol: str = "BTC/USDT") -> dict:
    """Send protective order(s) on futures venue. Best-effort stub.

    In real integration, place a market/stop order sized to partially or fully hedge the exposure.
    """
    try:
        # Best-effort: use ccxt spot as proxy; real futures integration can replace this
        from traders_core.connectors.crypto_ccxt import _mk_exchange as mk_ex  # type: ignore

        ex = mk_ex(futures_venue, False)
        t = ex.safe_fetch_ticker(symbol) if hasattr(ex, "safe_fetch_ticker") else ex.fetch_ticker(symbol)
        px = float(t.get("last") or t.get("close") or 0.0)
        if px <= 0:
            return {"ok": False, "error": "price_unavailable"}
        qty = float(exposure_usd) / px
        # hedge by selling spot (proxy) – replace with futures short on integration
        res = ex.safe_place_order(symbol, "sell", qty) if hasattr(ex, "safe_place_order") else ex.create_market_sell_order(symbol, qty)
        return {"ok": True, "venue": futures_venue, "notional_usd": float(exposure_usd), "qty": float(qty), "px": px, "result": res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


__all__ = ["FlashCrashParams", "FlashCrashGuard", "emergency_hedge"]
