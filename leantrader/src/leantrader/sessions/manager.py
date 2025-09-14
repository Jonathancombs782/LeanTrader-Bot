from dataclasses import dataclass, field
from typing import Dict

import pandas as pd

# Default session windows in UTC
SESSIONS = {
    "asia": (0, 8),  # 00:00 - 08:00
    "london": (8, 16),  # 08:00 - 16:00
    "ny": (13, 21),  # 13:00 - 21:00 overlaps
}


@dataclass
class SessionStats:
    trades: int = 0
    wins: int = 0
    pnl: float = 0.0
    sharpe_like: float = 0.0


@dataclass
class SessionBook:
    pair: str
    stats: Dict[str, SessionStats] = field(default_factory=lambda: {k: SessionStats() for k in SESSIONS.keys()})


def which_session(ts: pd.Timestamp) -> str:
    h = ts.tz_convert("UTC").hour if ts.tzinfo else ts.hour
    for name, (start, end) in SESSIONS.items():
        # allow wrap-around
        if start <= end:
            if start <= h < end:
                return name
        else:
            if h >= start or h < end:
                return name
    return "asia"  # default


def update_session_stats(book: SessionBook, session: str, pnl: float, win: bool):
    st = book.stats[session]
    st.trades += 1
    st.wins += int(win)
    st.pnl += pnl
    # naive rolling score; refine with real volatility-adjusted Sharpe later
    st.sharpe_like = (st.pnl / max(1, st.trades)) * st.wins / max(1, st.trades)
