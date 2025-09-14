"""
Auto trading loop (polling-based). Replace CSV input with live feeds & broker for production.
"""

import os
import time

from ..data.feeds import get_ohlc_csv, resample_frames
from .signal_service import generate_signals


def autotrade(pair: str, m15_csv: str, sleep_s: int = 30):
    while True:
        if os.path.exists(m15_csv):
            df = get_ohlc_csv(m15_csv)
            frames = resample_frames(df)
            generate_signals(frames, pair, post=True, min_confluence=3)
        time.sleep(sleep_s)
