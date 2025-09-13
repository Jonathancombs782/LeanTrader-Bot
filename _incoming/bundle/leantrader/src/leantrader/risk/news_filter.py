from datetime import datetime, timedelta

import pandas as pd

# Placeholder: in production, fetch from Forex Factory / Investing.com / Econoday / API.
# Here we allow manually feeding events.


class NewsCalendar:
    def __init__(self):
        self.events = []  # list of dict(time, impact, currency, desc)

    def add_event(self, time: datetime, impact: str, currency: str, desc: str):
        self.events.append({"time": time, "impact": impact, "currency": currency, "desc": desc})

    def is_blackout(self, now: datetime, pair: str, lookahead_min: int = 30) -> bool:
        # Return True if high impact news upcoming within lookahead for pair's base/quote currencies
        watch = [pair[:3], pair[-3:]]  # naive parse
        for ev in self.events:
            if ev["impact"].lower() == "high" and any(c in ev["currency"] for c in watch):
                if 0 <= (ev["time"] - now).total_seconds() / 60 <= lookahead_min:
                    return True
        return False
