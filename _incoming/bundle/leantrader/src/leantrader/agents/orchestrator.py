import multiprocessing as mp
import os
import time
from typing import Dict

import pandas as pd

from ..data.feeds import get_ohlc_csv, resample_frames
from ..live.signal_service import generate_signals


def worker(pair: str, csv_path: str, sleep_s: int = 30):
    while True:
        if os.path.exists(csv_path):
            df = get_ohlc_csv(csv_path)
            frames = resample_frames(df)
            generate_signals(frames, pair)
        time.sleep(sleep_s)


def spawn_agents(tasks: Dict[str, str], sleep_s: int = 30):
    # tasks: {pair: path_to_m15_csv}
    procs = []
    for pair, path in tasks.items():
        p = mp.Process(target=worker, args=(pair, path, sleep_s), daemon=True)
        p.start()
        procs.append(p)
    return procs
