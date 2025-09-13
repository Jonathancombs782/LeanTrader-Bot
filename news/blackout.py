from __future__ import annotations

import csv
import os
import time
from pathlib import Path
from typing import Optional


def _currency_from_symbol(symbol: str) -> Optional[str]:
    s = symbol.replace("/", "").upper()
    # crude mapping: prefer quote side USD/USDT
    if "USD" in s:
        return "USD"
    if len(s) == 6:
        return s[0:3]
    return None


def is_high_impact_soon(symbol: str, minutes: int = 15) -> bool:
    if os.getenv("NEWS_BLACKOUT_ENABLED", "false").strip().lower() not in ("1", "true", "yes", "on"):
        return False
    cur = _currency_from_symbol(symbol) or "USD"
    root = Path("data")
    for name in ("calendar.csv", "calender.csv"):
        p = root / name
        if not p.exists():
            continue
        try:
            now = time.time()
            window = minutes * 60
            with p.open("r", encoding="utf-8") as f:
                rdr = csv.DictReader(f)
                for row in rdr:
                    try:
                        cc = (row.get("currency") or row.get("curr") or "").upper()
                        imp = (row.get("impact") or row.get("importance") or "").lower()
                        ts_raw = row.get("time") or row.get("timestamp")
                        if not (ts_raw and cc):
                            continue
                        try:
                            ts = float(ts_raw)
                            if ts > 1e12:
                                ts = ts / 1000.0
                        except Exception:
                            # naive parse: YYYY-MM-DD HH:MM
                            try:
                                import datetime as _dt

                                ts = _dt.datetime.fromisoformat(ts_raw).timestamp()
                            except Exception:
                                continue
                        if cc == cur and imp in ("high", "3", "red") and 0 <= ts - now <= window:
                            return True
                    except Exception:
                        continue
        except Exception:
            continue
    return False

