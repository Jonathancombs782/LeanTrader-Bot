import random
import time
from dataclasses import dataclass
from typing import Dict


@dataclass
class EmuOrder:
    id: str
    symbol: str
    side: str
    qty: float
    price: float
    filled: float = 0.0
    status: str = "submitted"


class BrokerEmulator:
    def __init__(self, slippage_bps: float = 2.0, mean_latency_ms: int = 150):
        self.slip = slippage_bps
        self.lat = mean_latency_ms / 1000.0
        self.orders: Dict[str, EmuOrder] = {}

    def _oid(self):
        return f"emu-{int(time.time()*1000)}-{random.randint(100,999)}"

    def market(self, symbol: str, side: str, qty: float, ref_price: float) -> Dict:
        oid = self._oid()
        # Simulate latency
        time.sleep(max(0.0, random.gauss(self.lat, self.lat * 0.2)))
        # Simulate slippage (bps)
        slip = (self.slip / 10000.0) * ref_price * (1 if side.lower() == "buy" else -1)
        avg_fill_px = ref_price + slip
        # Simulate partials
        filled1 = qty * random.uniform(0.4, 0.7)
        time.sleep(0.05)
        filled2 = qty - filled1
        self.orders[oid] = EmuOrder(
            id=oid, symbol=symbol, side=side, qty=qty, price=avg_fill_px, filled=qty, status="filled"
        )
        return {
            "id": oid,
            "symbol": symbol,
            "side": side,
            "filled": qty,
            "avg_px": avg_fill_px,
            "status": "filled",
            "partials": [filled1, filled2],
        }
