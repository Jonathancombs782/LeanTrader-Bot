from traders_core.execution.fills_logger import on_fill

def record_fill(symbol: str, side: str, price: float, qty: float,
                fee: float = 0.0, fee_ccy: str = "", order_id: str = "",
                trade_id: str = "", strategy: str = "", exchange: str = ""):
    evt = {
        "symbol": symbol, "side": side, "price": price, "qty": qty,
        "fee": fee, "fee_ccy": fee_ccy, "order_id": order_id,
        "trade_id": trade_id, "strategy": strategy, "exchange": exchange,
    }
    on_fill(evt)

