# session_clock.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional

LONDON = ZoneInfo("Europe/London")
NEWYORK = ZoneInfo("America/New_York")
TOKYO = ZoneInfo("Asia/Tokyo")
SYDNEY = ZoneInfo("Australia/Sydney")

@dataclass
class Window:
    tz: ZoneInfo
    start: time
    end: time

# Core sessions (local clock in each region)
LONDON_WIN  = Window(LONDON,  time(7, 0),  time(17, 0))
NEWYORK_WIN = Window(NEWYORK, time(8, 0),  time(17, 0))
TOKYO_WIN   = Window(TOKYO,   time(9, 0),  time(18, 0))
SYDNEY_WIN  = Window(SYDNEY,  time(9, 0),  time(18, 0))

def _in_window(win: Window, now_utc: datetime) -> bool:
    now_local = now_utc.astimezone(win.tz)
    start = datetime.combine(now_local.date(), win.start, tzinfo=win.tz)
    end   = datetime.combine(now_local.date(), win.end,   tzinfo=win.tz)
    return start <= now_local <= end

def fx_session_active(symbol: str, now_utc: Optional[datetime] = None) -> bool:
    """
    Session logic:
      - Pairs with EUR/GBP => London
      - USD majors => New York
      - JPY => Tokyo
      - AUD/NZD => Sydney
      - Metals (XAU, XAG) => London + New York
      - If overlap (London+NY) => treated as active
    """
    s = symbol.upper()
    now_utc = now_utc or datetime.now(timezone.utc)
    base = s.replace(":", "/").split("/")[0]

    is_london = any(k in s for k in ("EUR", "GBP", "XAU", "XAG"))
    is_newyork = any(k in s for k in ("USD", "XAU", "XAG"))
    is_tokyo = "JPY" in s
    is_sydney = any(k in s for k in ("AUD", "NZD"))

    active = False
    if is_london:  active |= _in_window(LONDON_WIN, now_utc)
    if is_newyork: active |= _in_window(NEWYORK_WIN, now_utc)
    if is_tokyo:   active |= _in_window(TOKYO_WIN, now_utc)
    if is_sydney:  active |= _in_window(SYDNEY_WIN, now_utc)
    return active

def minutes_to_next_open(symbol: str, now_utc: Optional[datetime] = None) -> int:
    now_utc = now_utc or datetime.now(timezone.utc)
    if fx_session_active(symbol, now_utc):
        return 0

    wins = []
    s = symbol.upper()
    if any(k in s for k in ("EUR","GBP","XAU","XAG")): wins.append(LONDON_WIN)
    if "USD" in s or any(k in s for k in ("XAU","XAG")): wins.append(NEWYORK_WIN)
    if "JPY" in s: wins.append(TOKYO_WIN)
    if any(k in s for k in ("AUD","NZD")): wins.append(SYDNEY_WIN)
    if not wins:
        return 60

    mins_list = []
    for w in wins:
        now_local = now_utc.astimezone(w.tz)
        start = datetime.combine(now_local.date(), w.start, tzinfo=w.tz)
        if now_local <= start:
            mins_list.append(int((start - now_local).total_seconds() // 60))
        else:
            # next day
            start = start + timedelta(days=1)
            mins_list.append(int((start - now_local).total_seconds() // 60))
    return min(mins_list) if mins_list else 60
