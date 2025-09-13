"""Signal policy dispatcher and confluence scorers.

Fuses TA features with (optional) news scores and session weights learned
by the online learner to produce BUY/SELL/HOLD decisions.

All heavy deps are optional and gated; absence yields graceful defaults.
"""

import os
from datetime import timezone
from typing import Dict, List, Tuple

import pandas as pd

try:
    from ..news.feeds import fetch_rss
    from ..news.scorer import score_by_symbol
except Exception:
    fetch_rss = None  # type: ignore
    score_by_symbol = None  # type: ignore

try:
    from ..learn.online_learner import _load as _load_learn_state  # type: ignore
except Exception:

    def _load_learn_state():  # type: ignore
        return {"weights": {"session_tokyo": 1.0, "session_london": 1.0, "session_ny": 1.0}}


# Try to import house_smc or meta_router if present
try:
    from .house_smc import house_rules
except Exception:
    house_rules = None

try:
    from .meta_router import meta_route
except Exception:
    meta_route = None


def run_for_pair(pair: str, frames: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    # Prefer meta_router if available
    if meta_route is not None:
        try:
            return meta_route(pair, frames)
        except Exception:
            pass
    if house_rules is not None:
        try:
            return house_rules(pair, frames)
        except Exception:
            pass
    # Fallback: return empty DataFrame with expected columns
    idx = pd.DatetimeIndex([])
    return pd.DataFrame(index=idx, columns=["signal", "go", "side"])


# -------- Enhanced confluence --------
def _session_from_time(ts: pd.Timestamp) -> str:
    h = ts.tz_convert(timezone.utc).hour if ts.tzinfo else ts.hour
    if 0 <= h < 8:
        return "tokyo"
    if 8 <= h < 16:
        return "london"
    return "ny"


def _news_score_for(symbol: str) -> float:
    try:
        if fetch_rss is None or score_by_symbol is None:
            return 0.5
        feeds = (os.getenv("NEWS_FEEDS") or "").strip()
        if not feeds:
            return 0.5
        urls = [u.strip() for u in feeds.split(",") if u.strip()]
        items = fetch_rss(urls)
        import time as _t

        scores = score_by_symbol(items, _t.time())
        return float(scores.get(symbol.replace("/", ""), 0.5))
    except Exception:
        return 0.5


def fuse_confluence(symbol: str, row: pd.Series, ts: pd.Timestamp) -> Tuple[float, List[str]]:
    notes: List[str] = []
    # TA base
    ema20 = row.filter(like="ema_20").mean()
    ema50 = row.filter(like="ema_50").mean()
    sma200 = row.filter(like="sma_200").mean()
    rsi = row.filter(like="rsi_14").mean()
    macd_hist = row.filter(like="macd_hist").mean()
    volp = row.filter(like="atr_14").mean()
    base = 0.0
    if ema20 > ema50:
        base += 0.25
        notes.append("ema20>ema50")
    if ema50 > sma200:
        base += 0.25
        notes.append("ema50>sma200")
    if rsi and 45 <= rsi <= 70:
        base += 0.2
        notes.append("rsi")
    if macd_hist and macd_hist > 0:
        base += 0.2
        notes.append("macd")
    if volp:
        base += 0.05
        notes.append("vol")
    base = max(0.0, min(1.0, base))

    # News contribution
    news = _news_score_for(symbol)
    # Session weight
    sess = _session_from_time(ts)
    st = _load_learn_state()
    w_key = f"session_{sess}"
    sess_w = float(st.get("weights", {}).get(w_key, 1.0))
    sess_w = max(0.5, min(2.0, sess_w))

    # Blend: base 0.7, news 0.2, session scalar 0.1
    conf = max(0.0, min(1.0, 0.7 * base + 0.2 * news + 0.1 * (0.5 + (sess_w - 0.5) / 1.5)))
    if len(notes) < 3:
        notes.extend(["trend", "momentum", "volatility"])  # pad for UX
        notes = notes[:3]
    return conf, notes
