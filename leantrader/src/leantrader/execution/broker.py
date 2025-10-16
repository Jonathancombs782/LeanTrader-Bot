import time
from dataclasses import dataclass


@dataclass
class Order:
    id: str
    symbol: str
    side: str
    qty: float
    price: float
    status: str


class PaperBroker:
    def __init__(self, starting_balance: float = 10000.0):
        self.balance = starting_balance
        self.positions = {}

    def market(self, symbol: str, side: str, qty: float, price: float) -> Order:
        oid = f"paper-{int(time.time()*1000)}"
        return Order(id=oid, symbol=symbol, side=side, qty=qty, price=price, status="filled")


try:
    import ccxt
except Exception:
    ccxt = None


class CcxtBroker:
    def __init__(self, exchange: str, api_key: str = "", secret: str = "", password: str = "", sandbox: bool = False):
        assert ccxt is not None, "ccxt not installed"
        ex = getattr(ccxt, exchange)({"apiKey": api_key, "secret": secret, "password": password})
        if sandbox and hasattr(ex, "set_sandbox_mode"):
            ex.set_sandbox_mode(True)
        self.ex = ex

    def market(self, symbol: str, side: str, qty: float) -> dict:
        if side == "long" or side == "buy":
            o = self.ex.create_order(symbol, "market", "buy", qty)
        else:
            o = self.ex.create_order(symbol, "market", "sell", qty)
        return o


class FxBroker:
    """Placeholder for a real FX broker (e.g., Oanda, MT5 gateway).
    Implement: authenticate, market/limit orders, cancel, balances/positions."""

    def __init__(self, api_key: str = "", secret: str = "", **kw):
        self.api_key = api_key
        self.secret = secret

    def market(self, symbol: str, side: str, qty: float) -> dict:
        """Execute market order on FX broker.
        
        Note: This is a placeholder implementation. For production:
        - Integrate with Oanda API: https://developer.oanda.com/rest-live-v20/order-ep/
        - Or MT5 via MetaTrader5 Python package
        - Or use CCXT for forex-enabled brokers
        """
        try:
            # Placeholder for real broker implementation
            # Example for Oanda:
            # import requests
            # endpoint = f"https://api-fxtrade.oanda.com/v3/accounts/{account_id}/orders"
            # headers = {"Authorization": f"Bearer {self.api_key}"}
            # data = {
            #     "order": {
            #         "instrument": symbol,
            #         "units": qty if side == "buy" else -qty,
            #         "type": "MARKET"
            #     }
            # }
            # response = requests.post(endpoint, headers=headers, json=data)
            # return response.json()
            
            return {
                "status": "simulated",
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "message": "FX broker integration pending - using paper mode"
            }
        except Exception as e:
            return {
                "status": "error",
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "error": str(e)
            }
