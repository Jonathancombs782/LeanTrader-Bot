import os

from .broker_fx_mt5 import MT5Broker
from .broker_fx_oanda import OandaBroker


class FXBroker:
    def __init__(self, api_key: str = "", api_secret: str = "", **kwargs):
        self.backend = (os.getenv("FX_BACKEND", "oanda")).lower()
        self.api_key = api_key
        self.api_secret = api_secret
        self.kwargs = kwargs

    def market(self, symbol: str, side: str, qty: float) -> dict:
        # Runtime safety: require explicit ENABLE_LIVE + ALLOW_LIVE + LIVE_CONFIRM=YES
        # Otherwise, perform a dry-run and return a simulated response.
        enable_live = (os.getenv("ENABLE_LIVE", "").strip().lower() == "true")
        allow_live = (os.getenv("ALLOW_LIVE", "").strip().lower() in ("1", "true", "yes", "on")) and (
            os.getenv("LIVE_CONFIRM", "").strip().upper() == "YES"
        )
        if not (enable_live and allow_live):
            return {
                "ok": False,
                "dry_run": True,
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "note": "live disabled (ENABLE_LIVE/ALLOW_LIVE/LIVE_CONFIRM)",
            }
        if self.backend == "oanda":
            br = OandaBroker(
                api_token=self.api_key or os.getenv("OANDA_API_TOKEN", ""),
                account_id=os.getenv("OANDA_ACCOUNT_ID", ""),
                env=os.getenv("OANDA_ENV", "practice"),
            )
            return br.market(symbol, side, qty)
        elif self.backend == "mt5":
            br = MT5Broker()
            return br.market(symbol, side, qty)
        else:
            return {"status": "error", "error": f"Unsupported FX_BACKEND: {self.backend}"}
