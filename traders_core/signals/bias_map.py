import time
from typing import Dict

class BiasMap:
    def __init__(self):
        self._map: Dict[str, tuple[float,int]] = {}

    def set(self, symbol: str, bias: float, ttl_ms: int):
        bias = max(0.0, min(1.0, float(bias)))
        self._map[symbol.upper()] = (bias, int(time.time()*1000) + ttl_ms)

    def get(self, symbol: str) -> float:
        symbol = symbol.upper()
        now = int(time.time()*1000)
        b = self._map.get(symbol)
        if not b:
            return 0.0
        val, exp = b
        if now >= exp:
            self._map.pop(symbol, None)
            return 0.0
        return val

