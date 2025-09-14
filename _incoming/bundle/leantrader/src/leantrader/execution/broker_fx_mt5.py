import os

# MetaTrader5 connector stub. Requires `pip install MetaTrader5` and MT5 terminal running.

try:
    import MetaTrader5 as mt5
except Exception:
    mt5 = None


class MT5Broker:
    def __init__(self):
        if mt5 is None:
            raise RuntimeError("MetaTrader5 module not installed")
        if not mt5.initialize():
            raise RuntimeError("Failed to initialize MT5")

    def market(self, symbol: str, side: str, qty: float) -> dict:
        # Minimal example. You must adjust symbol mapping and volume steps per broker.
        action = mt5.TRADE_ACTION_DEAL
        order_type = mt5.ORDER_TYPE_BUY if side.lower() in ("buy", "long") else mt5.ORDER_TYPE_SELL
        req = {
            "action": action,
            "symbol": symbol.replace("/", ""),
            "volume": float(qty),
            "type": order_type,
            "deviation": 20,
            "magic": 20250908,
            "comment": "LeanTrader",
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(req)
        return {"retcode": getattr(res, "retcode", None), "comment": getattr(res, "comment", None)}
