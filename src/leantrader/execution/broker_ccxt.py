from __future__ import annotations

import os
from typing import Any, Dict


class BrokerCCXT:
    """Thin CCXT wrapper with strong safety guards.

    Live trading only proceeds when all flags are set:
      ENABLE_LIVE=true, ALLOW_LIVE=true, LIVE_CONFIRM=YES and API keys present.
    Otherwise behaves as dry-run and simulates a market result.
    """

    def __init__(self) -> None:
        self.exchange_id = (os.getenv("CCXT_EXCHANGE") or os.getenv("EXCHANGE_ID") or "bybit").lower()
        self.mode = (os.getenv("EXCHANGE_MODE") or "spot").lower()
        self.enable_live = os.getenv("ENABLE_LIVE", "false").lower() in ("1", "true", "yes")
        self.allow_live = os.getenv("ALLOW_LIVE", "false").lower() in ("1", "true", "yes")
        self.live_confirm = os.getenv("LIVE_CONFIRM", "").strip().upper() == "YES"
        self.api_key = os.getenv("API_KEY") or os.getenv(f"{self.exchange_id.upper()}_API_KEY") or ""
        self.api_secret = os.getenv("API_SECRET") or os.getenv(f"{self.exchange_id.upper()}_API_SECRET") or ""
        self.live = self.enable_live and self.allow_live and self.live_confirm and self.api_key and self.api_secret
        # lazy import ccxt and init only if live is explicitly allowed or for ticker fetch
        self._ccxt = None
        self._ex = None

    def _ensure_ex(self):
        if self._ex is not None:
            return
        try:
            import ccxt  # type: ignore

            self._ccxt = ccxt
            klass = getattr(ccxt, self.exchange_id)
            opts: Dict[str, Any] = {
                "enableRateLimit": True,
                "timeout": int(os.getenv("CCXT_TIMEOUT_MS", "15000")),
                "options": {},
            }
            if self.mode == "linear":
                if self.exchange_id == "bybit":
                    opts["options"]["defaultType"] = "swap"
                    opts["options"]["defaultSubType"] = "linear"
                elif self.exchange_id == "binance":
                    opts["options"]["defaultType"] = "future"
            if self.api_key and self.api_secret:
                opts["apiKey"] = self.api_key
                opts["secret"] = self.api_secret
            self._ex = klass(opts)
        except Exception as e:
            self._ex = None
            raise RuntimeError(f"ccxt init failed: {e}")

    def market(self, symbol: str, side: str, qty: float, ref_price: float) -> Dict[str, Any]:
        # dry-run safe default
        if not self.live:
            return {
                "ok": True,
                "simulated": True,
                "exchange": self.exchange_id,
                "symbol": symbol,
                "side": side,
                "price": float(ref_price or 0),
                "qty": float(qty or 0),
            }
        # live path
        self._ensure_ex()
        assert self._ex is not None
        try:
            params = {}
            order = self._ex.create_order(symbol, "market", side, qty, None, params)  # type: ignore[attr-defined]
            return {"ok": True, "order": order}
        except Exception as e:
            return {"ok": False, "error": str(e)}
