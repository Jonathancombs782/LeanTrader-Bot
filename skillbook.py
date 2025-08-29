# skillbook.py
from __future__ import annotations
import json, os
from typing import Tuple, Dict

_PATH = os.path.join("runtime", "skill_state.json")

def _load() -> Dict:
    try:
        with open(_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save(d: Dict) -> None:
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)
    tmp = _PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, _PATH)

def update_vol_stats(market: str, symbol: str, tf: str, atr_pct: float, bbw: float) -> None:
    """
    Simple EMA-style memory of recent vol per (market,symbol,tf).
    """
    d = _load()
    k = f"{market}:{symbol}:{tf}"
    row = d.get(k, {"atr": 0.0, "bbw": 0.0, "n": 0})
    n = float(row.get("n", 0)) + 1.0
    alpha = 0.2  # memory speed
    row["atr"] = (1 - alpha) * float(row.get("atr", 0.0)) + alpha * float(atr_pct)
    row["bbw"] = (1 - alpha) * float(row.get("bbw", 0.0)) + alpha * float(bbw)
    row["n"] = n
    d[k] = row
    _save(d)

def personalized_thresholds(symbol: str, base_atr_th: float, base_bbw_th: float) -> Tuple[float, float]:
    """
    For very volatile symbols (e.g., XAUUSD, BTC/USDT), nudge thresholds upward
    so the bot trades only in cleaner impulses; for quiet symbols, lower them a bit.
    """
    s = symbol.upper()
    vol_boost = 1.0
    if any(tag in s for tag in ("XAU", "XAG")):
        vol_boost = 1.25   # be choosier on gold/silver
    if any(tag in s for tag in ("BTC", "ETH")):
        vol_boost = max(vol_boost, 1.15)

    return base_atr_th * vol_boost, base_bbw_th * vol_boost
