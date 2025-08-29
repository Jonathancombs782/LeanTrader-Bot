# strategist.py
from typing import List, Tuple, Dict, Any

def ema(vals: List[float], n: int) -> List[float]:
    if not vals: return []
    a = 2/(n+1)
    out, e = [], vals[0]
    for v in vals:
        e = a*v + (1-a)*e
        out.append(e)
    return out

def breakout_signal(bars: List[List[float]]) -> Dict[str, Any]:
    """
    bars: [ [ts, open, high, low, close, vol], ... ]  (1m)
    rule: close > last 20-bar high & EMA(9) > EMA(21)  -> BUY
    """
    if len(bars) < 30: return {"side": None}
    closes = [b[4] for b in bars]
    highs  = [b[2] for b in bars]
    e9, e21 = ema(closes, 9), ema(closes, 21)
    last_close = closes[-1]
    last_e9, last_e21 = e9[-1], e21[-1]
    hh20 = max(highs[-21:-1])
    if last_close > hh20 and last_e9 > last_e21:
        return {"side": "buy", "entry": last_close}
    return {"side": None}
