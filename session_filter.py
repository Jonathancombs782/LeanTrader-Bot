# session_filter.py
# Tags current market session and returns weights for decision making.

from __future__ import annotations
import datetime as dt
from typing import Tuple

def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)

def fx_session_weight(symbol: str) -> Tuple[str, float]:
    """
    Returns (session_name, weight 0..1).
    London/NY overlap is strongest; weight per pair.
    """
    now = _utcnow().time()
    # Sessions in UTC (approx):
    asia   = (dt.time(23,0), dt.time(7,0))   # 23:00–07:00
    london = (dt.time(7,0),  dt.time(15,0))  # 07:00–15:00
    ny     = (dt.time(12,0), dt.time(20,0))  # 12:00–20:00

    def in_range(t0, t1, t) -> bool:
        return (t0 <= t <= t1) if t0 < t1 else (t >= t0 or t <= t1)

    if in_range(*asia, now):
        sess, w = "ASIA", 0.6
    elif in_range(*london, now) and in_range(*ny, now):
        sess, w = "LONDON-NY", 1.0
    elif in_range(*london, now):
        sess, w = "LONDON", 0.9
    elif in_range(*ny, now):
        sess, w = "NEWYORK", 0.9
    else:
        sess, w = "OFF", 0.5

    s = symbol.upper()
    if "EUR" in s or "GBP" in s:
        w *= 1.05 if "LONDON" in sess else 1.0
    if "JPY" in s or "AUD" in s or "NZD" in s:
        # Asia centered
        if sess == "ASIA": w *= 1.05
    if "XAU" in s or "XAG" in s:
        if sess in ("NEWYORK","LONDON-NY"): w *= 1.1

    return (sess, max(0.3, min(1.2, w)))

def crypto_session_weight(symbol: str) -> Tuple[str, float]:
    """
    Crypto runs 24/7; activity peaks with US hours.
    """
    now = _utcnow().time()
    ny_peak = (dt.time(13,0), dt.time(22,0))  # 13:00–22:00 UTC ~ NY business
    def in_range(t0, t1, t): return t0 <= t <= t1
    w = 1.0 if in_range(*ny_peak, now) else 0.85
    return ("CRYPTO", w)
