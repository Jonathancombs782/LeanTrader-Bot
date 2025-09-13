from __future__ import annotations

import os
from typing import Any, Dict


class BrokerFX:
    """FX broker adapter (OANDA/MT5) with strong safety guards.

    Default: dry-run simulation unless ENABLE_LIVE+ALLOW_LIVE+LIVE_CONFIRM and creds present.
    """

    def __init__(self) -> None:
        self.backend = (os.getenv("FX_BACKEND") or "").lower()  # "oanda" | "mt5"
        self.enable_live = os.getenv("ENABLE_LIVE", "false").lower() in ("1", "true", "yes")
        self.allow_live = os.getenv("ALLOW_LIVE", "false").lower() in ("1", "true", "yes")
        self.live_confirm = os.getenv("LIVE_CONFIRM", "").strip().upper() == "YES"
        self.live = self.enable_live and self.allow_live and self.live_confirm

    def market(self, symbol: str, side: str, qty: float, ref_price: float) -> Dict[str, Any]:
        if not self.live:
            return {
                "ok": True,
                "simulated": True,
                "backend": self.backend or "none",
                "symbol": symbol,
                "side": side,
                "price": float(ref_price or 0),
                "qty": float(qty or 0),
            }
        # Live paths
        if self.backend == "oanda":
            try:
                import oandapyV20.endpoints.orders as orders  # type: ignore
                from oandapyV20 import API  # type: ignore
            except Exception:
                return {"ok": False, "error": "oandapyV20 not installed (pip install oandapyV20)"}
            acct = os.getenv("OANDA_ACCOUNT") or ""
            tok = os.getenv("OANDA_TOKEN") or ""
            env = os.getenv("OANDA_ENV", "practice")
            if not (acct and tok):
                return {"ok": False, "error": "OANDA_ACCOUNT/TOKEN missing"}
            try:
                api = API(access_token=tok, environment=env)
                data = {
                    "order": {
                        "instrument": symbol.replace("/", "_"),
                        "units": str(int(qty if side == "buy" else -qty)),
                        "type": "MARKET",
                        "positionFill": "DEFAULT",
                    }
                }
                r = orders.OrderCreate(acct, data=data)
                resp = api.request(r)
                return {"ok": True, "order": resp}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        if self.backend == "mt5":
            try:
                import MetaTrader5 as mt5  # type: ignore
            except Exception:
                return {"ok": False, "error": "MetaTrader5 not installed"}
            path = os.getenv("MTS_PATH")
            ok = mt5.initialize(path=path)
            if not ok:
                return {"ok": False, "error": f"mt5.initialize failed: {mt5.last_error()}"}
            # Minimal market request (assuming symbol configured in terminal)
            action = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": float(qty),
                "type": action,
                "deviation": 20,
                "magic": 123456,
                "comment": "leantrader",
            }
            try:
                result = mt5.order_send(request)
                return {"ok": True, "order": {"retcode": result.retcode}}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "FX_BACKEND not configured (set FX_BACKEND=oanda|mt5)"}
