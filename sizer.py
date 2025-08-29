# sizer.py
from __future__ import annotations
import os, math, datetime as dt
from typing import Dict, Any, Optional

def _envf(k: str, d: float) -> float:
    try: return float(os.getenv(k, str(d)))
    except: return d

def _envi(k: str, d: int) -> int:
    try: return int(float(os.getenv(k, str(d))))
    except: return d

def _envb(k: str, d: bool) -> bool:
    return os.getenv(k, str(d)).strip().lower() in ("1","true","yes","y","on")

def _session_mult(now_utc: Optional[dt.datetime]=None) -> float:
    """Simple FX/crypto session throttle (UTC clock)."""
    now = now_utc or dt.datetime.utcnow()
    h = now.hour
    asia   = _envf("SESSION_ASIA",   0.7)   # 00:00–06:59
    london = _envf("SESSION_LONDON", 1.0)   # 07:00–12:59
    ny     = _envf("SESSION_NEWYORK",1.2)   # 13:00–20:59
    if 0 <= h < 7:   return asia
    if 7 <= h < 13:  return london
    if 13 <= h < 21: return ny
    return 0.85  # late US / rollover quieter

def suggest_size(signal: Dict[str,Any], equity_usd: float) -> Dict[str,Any]:
    """
    Returns sizing hints merged onto the signal:
      - qty (base units), notional_usd, risk_bps_eff, leverage (if futures), notes[]
    Inputs expected in signal:
      entry, sl, market ('fx' or 'crypto-*'), tf
    Env knobs:
      SIZER_MODE=fixed_usd|vol_target
      FIXED_USD (default 5)
      RISK_PER_TRADE_BPS (default 25 = 0.25%)
      MIN_NOTIONAL_USD (default 5)
      LEV_MIN, LEV_MAX (futures)
    """
    out = dict(signal)
    notes = list(out.get("context", []))

    price = float(out.get("entry", 0.0))
    sl    = float(out.get("sl", 0.0))
    if price <= 0 or sl <= 0 or price == sl:
        out.update({"qty": 0.0, "notional_usd": 0.0, "risk_bps_eff": 0.0})
        notes.append("sizer: bad price/SL")
        out["context"] = notes
        return out

    R = abs(price - sl)                             # $ risk per 1 unit
    mode = os.getenv("SIZER_MODE", "vol_target").lower()

    if mode == "fixed_usd":
        stake = _envf("FIXED_USD", 5.0) * _session_mult()
        qty = max(0.0, stake / R)
        risk_bps_eff = (stake / max(1e-9, equity_usd)) * 1e4
        notes.append(f"sizer: fixed ${stake:.2f}")
    else:
        risk_bps = _envf("RISK_PER_TRADE_BPS", 25.0)  # 0.25% default
        risk_usd = equity_usd * (risk_bps / 1e4) * _session_mult()
        qty = max(0.0, risk_usd / R)
        risk_bps_eff = risk_bps
        notes.append(f"sizer: vol_target {risk_bps:.1f}bps -> ${risk_usd:.2f} risk")

    # Notional & min
    notional_usd = qty * price
    min_notional = _envf("MIN_NOTIONAL_USD", 5.0)
    if notional_usd < min_notional:
        scale = (min_notional / max(1e-9, notional_usd))
        qty *= scale
        notional_usd = qty * price
        notes.append(f"sizer: upscaled to min ${min_notional:.2f}")

    # Leverage suggestion (for futures)
    lev = None
    if str(out.get("market","")).startswith("crypto-") and os.getenv("EXCHANGE_MODE","spot") == "linear":
        # Use ATR% proxy from TP ladder (if present) or ATR note in context
        atr_pct = abs(price - sl) / max(1e-9, price)  # ~1R as ATR-ish
        # map atr% to leverage: smaller ATR% -> can size higher
        lev_min = _envi("LEV_MIN", 2); lev_max = _envi("LEV_MAX", 6)
        # e.g., atr 0.3% -> high lev, atr 2% -> low lev
        lev = int(max(lev_min, min(lev_max, round((0.012 / max(1e-6, atr_pct))))))
        notes.append(f"sizer: lev≈{lev} (atr≈{atr_pct*100:.2f}%)")

    out.update({
        "qty": float(qty),
        "notional_usd": float(notional_usd),
        "risk_bps_eff": float(risk_bps_eff),
        "leverage": lev
    })
    out["context"] = notes
    return out
