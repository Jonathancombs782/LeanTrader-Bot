# execution_adv.py
from typing import Dict, Any
from order_utils import place_market, safe_create_order

class LimitMakerExecutor:
    """
    Maker-only limit order helper (postOnly when supported by the exchange).
    Use on thin books to reduce taker fees/slippage. Falls back safely.
    """
    def __init__(self, ex, logger, fee_frac: float = 0.001):
        self.ex = ex
        self.log = logger
        self.fee_frac = fee_frac

    def limit_maker_buy(self, symbol: str, price: float, amount: float) -> Dict[str, Any]:
        params = {"postOnly": True}
        try:
            # Prefer safe wrapper, then create_order, then router-level helpers
            if hasattr(self.ex, 'safe_place_order'):
                order = self.ex.safe_place_order(symbol, "buy", amount, price=price, params=params)
            elif hasattr(self.ex, 'place_spot_market'):
                # ExchangeRouter-style helper: returns {ok: bool, result: ...}
                res = self.ex.place_spot_market(symbol, "buy", qty=amount)
                order = res.get("result") if isinstance(res, dict) else res
            elif hasattr(self.ex, 'create_limit_order'):
                try:
                    order = self.ex.create_limit_order(symbol, "buy", amount, price)
                except Exception:
                    order = None
            elif hasattr(self.ex, 'create_order'):
                try:
                    order = safe_create_order(self.ex, 'limit', symbol, 'buy', amount, price, params=params)
                except Exception:
                    order = None
            else:
                raise RuntimeError("no order method available on exchange")
            self.log.info(f"POST-ONLY BUY {symbol} px={price} amt={amount}")
            return order
        except Exception as e:
            self.log.warning(f"postOnly failed, fallback to limit BUY: {e}")
            # best-effort fallbacks
            try:
                if hasattr(self.ex, 'safe_place_order'):
                    return self.ex.safe_place_order(symbol, "buy", amount, price=price)
                if hasattr(self.ex, 'place_spot_market'):
                    return self.ex.place_spot_market(symbol, "buy", qty=amount)
                if hasattr(self.ex, 'create_limit_order'):
                    try:
                        return self.ex.create_limit_order(symbol, "buy", amount, price)
                    except Exception:
                        pass
                if hasattr(self.ex, 'create_order'):
                    try:
                        return safe_create_order(self.ex, 'limit', symbol, 'buy', amount, price)
                    except Exception:
                        pass
                # last resort: place market using helper
                return place_market(self.ex, symbol, "buy", amount)
            except Exception:
                pass
            return {"ok": False, "error": "no order method available"}

    def limit_maker_sell(self, symbol: str, price: float, amount: float) -> Dict[str, Any]:
        params = {"postOnly": True}
        try:
            if hasattr(self.ex, 'safe_place_order'):
                order = self.ex.safe_place_order(symbol, "sell", amount, price=price, params=params)
            elif hasattr(self.ex, 'place_spot_market'):
                res = self.ex.place_spot_market(symbol, "sell", qty=amount)
                order = res.get("result") if isinstance(res, dict) else res
            elif hasattr(self.ex, 'create_limit_order'):
                try:
                    order = self.ex.create_limit_order(symbol, "sell", amount, price)
                except Exception:
                    order = None
            elif hasattr(self.ex, 'create_order'):
                try:
                    order = safe_create_order(self.ex, 'limit', symbol, 'sell', amount, price, params=params)
                except Exception:
                    order = None
            else:
                raise RuntimeError("no order method available on exchange")
            self.log.info(f"POST-ONLY SELL {symbol} px={price} amt={amount}")
            return order
        except Exception as e:
            self.log.warning(f"postOnly failed, fallback to limit SELL: {e}")
            try:
                if hasattr(self.ex, 'safe_place_order'):
                    return self.ex.safe_place_order(symbol, "sell", amount, price=price)
                if hasattr(self.ex, 'place_spot_market'):
                    return self.ex.place_spot_market(symbol, "sell", qty=amount)
                if hasattr(self.ex, 'create_limit_order'):
                    try:
                        return self.ex.create_limit_order(symbol, "sell", amount, price)
                    except Exception:
                        pass
                if hasattr(self.ex, 'create_order'):
                    try:
                        return safe_create_order(self.ex, 'limit', symbol, 'sell', amount, price)
                    except Exception:
                        pass
                return place_market(self.ex, symbol, "sell", amount)
            except Exception:
                pass
            return {"ok": False, "error": "no order method available"}
    def safe_cancel(self, order_id: str, symbol: str) -> None:
        try:
            if hasattr(self.ex, 'safe_cancel_order'):
                try:
                    self.ex.safe_cancel_order(order_id, symbol)
                except Exception as e:
                    print(f"[execution_adv] safe_cancel_order failed: {e}")
            elif hasattr(self.ex, 'cancel_order'):
                try:
                    self.ex.cancel_order(order_id, symbol)
                except Exception as e:
                    print(f"[execution_adv] cancel_order failed: {e}")
            elif hasattr(self.ex, 'place_spot_market') and hasattr(self.ex, 'get_order_status'):
                # last-resort: router-style exchange may provide a cancel helper
                try:
                    self.ex.safe_cancel_order(order_id, symbol)
                except Exception:
                    pass
            else:
                raise RuntimeError("no cancel method available")
            self.log.info(f"CANCELLED {symbol} order_id={order_id}")
        except Exception as e:
            try:
                self.log.error(f"Failed to cancel {symbol} order_id={order_id}: {e}")
            except Exception:
                print(f"[execution_adv] Failed to cancel {symbol} order_id={order_id}: {e}")
    def get_order_status(self, order_id: str, symbol: str) -> Dict[str, Any]:
        try:
            # prefer explicit helper, then ccxt fetch_order; guard exceptions
            if hasattr(self.ex, 'get_order_status'):
                try:
                    status = self.ex.get_order_status(order_id, symbol)
                except Exception as e:
                    print(f"[execution_adv] get_order_status helper failed: {e}")
                    status = {}
            elif hasattr(self.ex, 'safe_fetch_order'):
                try:
                    status = self.ex.safe_fetch_order(order_id, symbol)
                except Exception as e:
                    print(f"[execution_adv] safe_fetch_order failed: {e}")
                    status = {}
            elif hasattr(self.ex, 'fetch_order'):
                try:
                    status = self.ex.fetch_order(order_id, symbol)
                except Exception as e:
                    print(f"[execution_adv] fetch_order failed: {e}")
                    status = {}
            else:
                status = {"error": "no order status method available"}
            try:
                self.log.info(f"ORDER STATUS {symbol} order_id={order_id}: {status}")
            except Exception:
                print(f"[execution_adv] ORDER STATUS {symbol} order_id={order_id}: {status}")
            return status or {}
        except Exception as e:
            try:
                self.log.error(f"Failed to get {symbol} order_id={order_id} status: {e}")
            except Exception:
                print(f"[execution_adv] Failed to get {symbol} order_id={order_id} status: {e}")
            return {"error": str(e)}
        