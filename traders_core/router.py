# router.py
import os
from pprint import pprint
from typing import Any, Dict, List

import ccxt

from order_utils import place_market, safe_create_order
from paper_broker import PaperBroker  # already in your repo


class ExchangeRouter:
    def __init__(self):
        self.mode = os.getenv("EXCHANGE_MODE", "spot").lower()  # spot | linear
        self.live = os.getenv("ENABLE_LIVE", "false").lower() == "true"
        self.paper = os.getenv("EXCHANGE_ID", "paper").lower() == "paper"
        self.testnet = os.getenv("BYBIT_TESTNET", "false").lower() == "true"
        self.quote_as_notional = os.getenv("CCXT_QUOTE_AS_NOTIONAL", "true").lower() == "true"

        if self.paper:
            start_cash = float(os.getenv("PAPER_START_CASH", "5000"))
            self.ex = PaperBroker(start_cash)
        else:
            ex_id = os.getenv("EXCHANGE_ID", "bybit")
            apiKey = os.getenv("API_KEY", "")
            secret = os.getenv("API_SECRET", "")
            opts = {"enableRateLimit": True}
            if ex_id == "bybit" and self.testnet:
                opts["urls"] = {
                    "api": "https://api-testnet.bybit.com",
                }

            self.ex = getattr(
                ccxt,
                ex_id,
            )(
                {
                    "apiKey": apiKey,
                    "secret": secret,
                    **opts,
                }
            )

        try:
            # try ccxt load_markets; some adapters return odd types
            if hasattr(self.ex, "load_markets"):
                self.markets = self.ex.load_markets()
            elif hasattr(self.ex, "fetch_markets"):
                self.markets = self.ex.fetch_markets()
            else:
                self.markets = {}
        except Exception as _e:
            print("[router] load_markets error:", _e)
            self.markets = {}

    # -------- info / account --------
    def info(self) -> Dict[str, Any]:
        return {
            "paper": self.paper,
            "testnet": self.testnet,
            "mode": self.mode,
            "live": self.live,
        }

    def account(self) -> Dict[str, Any]:
        try:
            if self.paper:
                return {
                    "ok": True,
                    "paper_cash": getattr(self.ex, "cash", 0.0),
                }
            if hasattr(self.ex, "safe_fetch_balance"):
                return {"ok": True, "balance": self.ex.safe_fetch_balance()}
            try:
                return {"ok": True, "balance": self.ex.fetch_balance()}
            except Exception:
                # fallback to an empty balance instead of raising
                return {"ok": True, "balance": {}}
        except Exception as _e:
            return {"ok": False, "error": str(_e)}

    def sample_symbols(self) -> List[str]:
        seeds = [
            "BTC/USDT",
            "ETH/USDT",
            "SOL/USDT",
            "XRP/USDT",
            "DOGE/USDT",
        ]
        return [s for s in seeds if s in self.markets]

    # -------- data helpers --------
    def fetch_ohlcv(self, symbol: str, tf: str = "1m", limit: int = 120):
        # Prefer router's safe wrapper when available.
        # Fall back to direct exchange fetch with guarded errors.
        ex = getattr(self, "ex", None)
        try:
            if ex is None:
                return []
            if hasattr(ex, "safe_fetch_ohlcv"):
                return ex.safe_fetch_ohlcv(symbol, timeframe=tf, limit=limit)
            try:
                return ex.fetch_ohlcv(
                    symbol,
                    timeframe=tf,
                    limit=limit,
                )
            except Exception as _e:
                print(
                    "[traders_core.router] fetch_ohlcv raw fetch failed for",
                    symbol,
                    _e,
                )
                return []
        except Exception as _e:
            print("[traders_core.router] fetch_ohlcv error for", symbol, _e)
            return []

    def last_price(self, symbol: str) -> float:
        try:
            if hasattr(self.ex, "safe_fetch_ticker"):
                t = self.ex.safe_fetch_ticker(symbol)
            else:
                t = self.ex.fetch_ticker(symbol)
            return float(t.get("last") or t.get("close") or 0)
        except Exception:
            return 0.0

    # -------- spot --------
    def place_spot_market(self, symbol: str, side: str, qty: float = None, notional: float = None):
        try:
            if notional and self.quote_as_notional:
                px = self.last_price(symbol)
                qty = float(notional) / px
            # prefer router/adapter safe helpers first
            if hasattr(self.ex, "safe_place_order"):
                order = self.ex.safe_place_order(symbol, side, qty)
            elif hasattr(self.ex, "create_order"):
                try:
                    order = safe_create_order(self.ex, "market", symbol, side, qty)
                except Exception:
                    order = place_market(self.ex, symbol, side, qty)
            else:
                # last-resort: use shared helper; it has internal fallbacks
                order = place_market(self.ex, symbol, side, qty)

            # Normalize result: if the underlying adapter returned an error dict
            if isinstance(order, dict) and (order.get("ok") is False or order.get("error")):
                return {"ok": False, "error": order.get("error") or order}
            return {"ok": True, "result": order}
        except Exception as _e:
            return {"ok": False, "error": str(_e)}

    # -------- linear futures (USDT-perp) --------
    def place_futures_market(
        self,
        symbol: str,
        side: str,
        qty: float,
        leverage: int = None,
        close: bool = False,
    ):
        try:
            params = {}
            if leverage and hasattr(self.ex, "set_leverage"):
                try:
                    self.ex.set_leverage(leverage, symbol)
                except Exception:
                    # ignore errors when setting leverage
                    pass
            if close:
                params["reduceOnly"] = True
            if hasattr(self.ex, "safe_place_order"):
                order = self.ex.safe_place_order(
                    symbol,
                    side,
                    qty,
                    params=params,
                )
            elif hasattr(self.ex, "create_order"):
                try:
                    order = safe_create_order(
                        self.ex,
                        "market",
                        symbol,
                        side,
                        qty,
                        price=None,
                        params=params,
                    )
                except Exception:
                    order = place_market(self.ex, symbol, side, qty)
            else:
                order = place_market(self.ex, symbol, side, qty)
            if isinstance(order, dict) and (order.get("ok") is False or order.get("error")):
                return {"ok": False, "error": order.get("error") or order}
            return {"ok": True, "result": order}
        except Exception as _e:
            return {"ok": False, "error": str(_e)}

    # -------- quick scanner --------
    def scan_top_movers(self, topn: int = 10, quote: str = "USDT", limit: int = 120):
        movers = []
        for sym in list(self.markets.keys()):
            if not sym.endswith("/" + quote):
                continue

            try:
                bars = self.fetch_ohlcv(
                    sym,
                    "1m",
                    limit=limit,
                )
                if not bars:
                    continue

                c0 = bars[0][4]
                c1 = bars[-1][4]
                change = (c1 - c0) / c0
                movers.append(
                    {
                        "symbol": sym,
                        "change": change,
                        "last": c1,
                    }
                )
            except Exception:
                # ignore symbol-level errors
                pass
        movers.sort(
            key=lambda x: x["change"],
            reverse=True,
        )
        return movers[:topn]


if __name__ == "__main__":
    r = ExchangeRouter()
    pprint(r.info())
    pprint(r.account())
    pprint(r.sample_symbols())
    pprint(r.scan_top_movers(5))
