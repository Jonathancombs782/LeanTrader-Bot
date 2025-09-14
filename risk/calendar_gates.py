from __future__ import annotations

import csv
import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import List, Dict, Optional


CAL_DIR = os.path.join("data", "calendar")
FX_FILE = os.path.join(CAL_DIR, "fx_macro.csv")
CRYPTO_FILE = os.path.join(CAL_DIR, "crypto_events.csv")
MAINT_FILE = os.path.join(CAL_DIR, "maintenance.csv")


def _parse_ts(s: str) -> Optional[datetime]:
    try:
        # Accept ISO 8601 or epoch seconds
        s = (s or "").strip()
        if not s:
            return None
        if s.isdigit():
            return datetime.fromtimestamp(int(s), tz=timezone.utc)
        # Fallback to fromisoformat with Z handling
        s2 = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s2).astimezone(timezone.utc)
    except Exception:
        return None


def _load_csv(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [dict(row) for row in reader]
    except Exception:
        return []


@lru_cache(maxsize=16)
def _events_fx() -> List[Dict[str, str]]:
    return _load_csv(FX_FILE)


@lru_cache(maxsize=16)
def _events_crypto() -> List[Dict[str, str]]:
    return _load_csv(CRYPTO_FILE)


@lru_cache(maxsize=16)
def _events_maint() -> List[Dict[str, str]]:
    return _load_csv(MAINT_FILE)


def _within_window(ts: Optional[datetime], now_utc: datetime, lookahead_min: int) -> bool:
    if ts is None:
        return False
    start = now_utc
    end = now_utc + timedelta(minutes=int(lookahead_min))
    return start <= ts <= end


def is_high_impact_window(now_utc: datetime, lookahead_min: int = 30) -> bool:
    for row in _events_fx():
        ts = _parse_ts(row.get("timestamp") or row.get("ts") or row.get("time") or "")
        if _within_window(ts, now_utc, lookahead_min):
            # optional severity filter
            sev = (row.get("severity") or "").lower()
            if not sev or sev in ("high", "red"):
                return True
    return False


def is_crypto_event_window(now_utc: datetime, lookahead_min: int = 30) -> bool:
    for row in _events_crypto():
        ts = _parse_ts(row.get("timestamp") or row.get("ts") or row.get("time") or "")
        if _within_window(ts, now_utc, lookahead_min):
            return True
    return False


def is_exchange_maintenance(exchange: str, now_utc: datetime, lookahead_min: int = 30) -> bool:
    ex = (exchange or "").strip().lower()
    for row in _events_maint():
        ts = _parse_ts(row.get("timestamp") or row.get("ts") or row.get("time") or "")
        ven = (row.get("exchange") or row.get("venue") or "").strip().lower()
        if ven and ven == ex and _within_window(ts, now_utc, lookahead_min):
            return True
    return False


def risk_gate(now_utc: datetime, exchange: Optional[str] = None) -> Dict[str, object]:
    reasons: List[str] = []
    block = False
    throttle = {"lambda_max": 0.4, "size_cap": 0.5}
    if is_high_impact_window(now_utc):
        reasons.append("fx_macro_high_impact")
        block = True
    if is_crypto_event_window(now_utc):
        reasons.append("crypto_event")
        block = block or True
    if exchange and is_exchange_maintenance(exchange, now_utc):
        reasons.append(f"maintenance:{exchange}")
        block = block or True
    return {"block": bool(block), "reasons": reasons, "throttle": throttle if not block else throttle}


__all__ = [
    "is_high_impact_window",
    "is_crypto_event_window",
    "is_exchange_maintenance",
    "risk_gate",
]

