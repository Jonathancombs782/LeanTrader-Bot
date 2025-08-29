# calendar_utils.py
from __future__ import annotations

import os
import csv
import datetime as dt
from pathlib import Path
from typing import Dict, Any, List

DATA_DIR = Path("data")
CAL_PATH = DATA_DIR / "calendar.csv"

# Simple currency tags for FX pairs
def _fx_tags(symbol: str) -> List[str]:
    s = symbol.replace("/", "")
    if len(s) >= 6:
        return [s[:3].upper(), s[3:6].upper()]
    return [symbol[:3].upper()]

def _parse_row(row: Dict[str, str]) -> Dict[str, Any]:
    # expected headers: time,currency,impact,event,forecast,previous
    out = dict(row)
    try:
        out["time"] = dt.datetime.fromisoformat(row["time"])
    except Exception:
        out["time"] = None
    out["currency"] = (row.get("currency") or "").upper()
    out["impact"] = (row.get("impact") or "").upper()
    return out

def _load_today_events() -> List[Dict[str, Any]]:
    if not CAL_PATH.exists():
        return []
    out = []
    with open(CAL_PATH, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rr = _parse_row(row)
            if rr["time"] is None:
                continue
            if rr["time"].date() == dt.datetime.utcnow().date():
                out.append(rr)
    return out

def risk_adjust_for_calendar(symbol: str, is_fx: bool) -> Dict[str, Any]:
    """
    Returns a dict with:
      - size_mult: float (<=1.0)
      - block_entries: bool
      - notes: str
    Very conservative around *HIGH* impact events on involved currencies within ±60 minutes.
    """
    if not is_fx:
        # for crypto we typically use USD macro only
        tags = ["USD"]
    else:
        tags = _fx_tags(symbol)

    events = _load_today_events()
    if not events:
        return {"size_mult": 1.0, "block_entries": False, "notes": ""}

    now = dt.datetime.utcnow()
    window_min = 60
    hit = []
    for e in events:
        if e["currency"] in tags and e["impact"] == "HIGH":
            delta = abs((e["time"] - now).total_seconds()) / 60.0
            if delta <= window_min:
                hit.append(e)

    if hit:
        titles = "; ".join([e["event"] for e in hit[:3]])
        return {
            "size_mult": 0.5,         # halve position around event
            "block_entries": True,    # block fresh entries in the window
            "notes": f"High-impact {tags} event within {window_min}m: {titles}"
        }
    return {"size_mult": 1.0, "block_entries": False, "notes": ""}
