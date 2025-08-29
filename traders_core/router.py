# router.py
import os, json
from typing import Dict, Any, List
from pprint import pprint
import ccxt

from paper_broker import PaperBroker  # already in your repo
from order_utils import place_market, safe_create_order

class ExchangeRouter:
    def __init__(self):
        self.mode    = os.getenv("EXCHANGE_MODE", "spot").lower()   # spot | linear
        self.live    = os.getenv("ENABLE_LIVE", "false").lower() == "true"
        self.paper   = os.getenv("EXCHANGE_ID", "paper").lower() == "paper"
        self.testnet = os.getenv("BYBIT_TESTNET", "false").lower() == "true"
        self.quote_as_notional = os.getenv("CCXT_QUOTE_AS_NOTIONAL", "true").lower() == "true"

        if self.paper:
            start_cash = float(os.getenv("PAPER_START_CASH", "5000"))
            self.ex = PaperBroker(start_cash)
        else:
            ex_id  = os.getenv("EXCHANGE_ID", "bybit")
            apiKey = os.getenv("API_KEY", "")
            secret = os.getenv("API_SECRET", "")
            opts = {"enableRateLimit": True}
            if ex_id == "bybit" and self.testnet:
                opts["urls"] = {"api": "https://api-testnet.bybit.com"}
            self.ex = getattr(ccxt, ex_id)({"apiKey": apiKey, "secret": secret, **opts})

        try:
            # try ccxt load_markets; some adapters return dicts/strings unexpectedly
            if hasattr(self.ex, 'load_markets'):
                self.markets = self.ex.load_markets()
            elif hasattr(self.ex, 'fetch_markets'):
                self.markets = self.ex.fetch_markets()
            else:
                self.markets = {}
        except Exception as e:
            print("[router] load_markets error:", e)
            self.markets = {}

    # -------- info / account --------
    def info(self) -> Dict[str, Any]:
        return {"paper": self.paper, "testnet": self.testnet, "mode": self.mode, "live": self.live}

    def account(self) -> Dict[str, Any]:
        try:
            if self.paper:
                return {"ok": True, "paper_cash": getattr(self.ex, 'cash', 0.0)}
            if hasattr(self.ex, 'safe_fetch_balance'):
                return {"ok": True, "balance": self.ex.safe_fetch_balance()}
            try:
                return {"ok": True, "balance": self.ex.fetch_balance()}
            except Exception:
                # fallback to an empty balance instead of raising
                return {"ok": True, "balance": {}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def sample_symbols(self) -> List[str]:
        seeds = ["BTC/USDT","ETH/USDT","SOL/USDT","XRP/USDT","DOGE/USDT"]
        return [s for s in seeds if s in self.markets]

    # -------- data helpers --------
    def fetch_ohlcv(self, symbol: str, tf: str = "1m", limit: int = 120):
        # Prefer exchange/router safe wrapper, but fall back to direct fetch with guarded errors
            ex = self._exchange_for(symbol)
            try:
                if hasattr(ex, 'safe_fetch_ohlcv'):
                    return ex.safe_fetch_ohlcv(symbol, timeframe=tf, limit=limit)
                try:
                    return ex.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
                except Exception as e:
                    print(f"[traders_core.router] fetch_ohlcv raw fetch failed for {symbol}: {e}")
                    return []
            except Exception as e:
                print(f"[traders_core.router] fetch_ohlcv error for {symbol}: {e}")
                return []

    def last_price(self, symbol: str) -> float:
        try:
            if hasattr(self.ex, 'safe_fetch_ticker'):
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
            if hasattr(self.ex, 'safe_place_order'):
                order = self.ex.safe_place_order(symbol, side, qty)
            elif hasattr(self.ex, 'create_order'):
                try:
                    from order_utils import safe_create_order
                    order = safe_create_order(self.ex, 'market', symbol, side, qty)
                except Exception:
                    order = place_market(self.ex, symbol, side, qty)
            else:
                # last-resort: use shared helper which contains its own fallbacks
                order = place_market(self.ex, symbol, side, qty)
            return {"ok": True, "result": order}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # -------- linear futures (USDT-perp) --------
    def place_futures_market(self, symbol: str, side: str, qty: float, leverage: int = None, close: bool = False):
        try:
            params = {}
            if leverage and hasattr(self.ex, "set_leverage"):
                try: self.ex.set_leverage(leverage, symbol)
                except: pass
            if close: params["reduceOnly"] = True
            if hasattr(self.ex, 'safe_place_order'):
                order = self.ex.safe_place_order(symbol, side, qty, params=params)
            elif hasattr(self.ex, 'create_order'):
                try:
                    from order_utils import safe_create_order
                    order = safe_create_order(self.ex, 'market', symbol, side, qty, price=None, params=params)
                except Exception:
                    order = place_market(self.ex, symbol, side, qty)
            else:
                order = place_market(self.ex, symbol, side, qty)
            return {"ok": True, "result": order}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # -------- quick scanner --------
    def scan_top_movers(self, topn: int = 10, quote: str = "USDT", limit: int = 120):
        movers = []
        for sym in list(self.markets.keys()):
            if not sym.endswith("/"+quote): continue
            try:
                bars = self.fetch_ohlcv(sym, "1m", limit=limit)
                if not bars: continue
                c0, c1 = bars[0][4], bars[-1][4]
                change = (c1 - c0) / c0
                movers.append({"symbol": sym, "change": change, "last": c1})
            except: pass
        movers.sort(key=lambda x: x["change"], reverse=True)
        return movers[:topn]

if __name__ == "__main__":
    r = ExchangeRouter()
    pprint(r.info()); pprint(r.account()); pprint(r.sample_symbols()); pprint(r.scan_top_movers(5))
