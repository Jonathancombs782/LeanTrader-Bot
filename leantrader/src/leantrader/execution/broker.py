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
        # TODO: implement real call
        return {"status": "todo_fx", "symbol": symbol, "side": side, "qty": qty}
