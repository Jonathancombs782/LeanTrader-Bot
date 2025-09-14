from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

LOG_DIR = Path(os.getenv("LEARN_LOG_DIR", "logs/learn"))
LOG_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Trade:
    ts: int
    symbol: str
    side: str
    r_mult: float


def write_trade(tr: Trade) -> None:
    p = LOG_DIR / "trades.csv"
    new = not p.exists()
    with open(p, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ts", "symbol", "side", "r_mult"])
        w.writerow([tr.ts, tr.symbol, tr.side, tr.r_mult])


def summarize(trades: List[Trade]) -> dict:
    if not trades:
        return {"n": 0, "winrate": 0.0, "avg_r": 0.0, "expectancy": 0.0}
    n = len(trades)
    wins = sum(1 for t in trades if t.r_mult > 0)
    avg_r = sum(t.r_mult for t in trades) / n
    winrate = wins / n
    # simplistic expectancy
    expectancy = avg_r
    return {"n": n, "winrate": winrate, "avg_r": avg_r, "expectancy": expectancy}
