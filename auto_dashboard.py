# auto_dashboard.py
# Summarize memory.jsonl → show what the bot has learned so far

import datetime as dt
import json
import pathlib
from collections import defaultdict

MEM_PATH = pathlib.Path("runtime/memory.jsonl")


def load_mem():
    if not MEM_PATH.exists():
        return []
    with MEM_PATH.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def summarize(rows):
    sym = defaultdict(lambda: {"n": 0, "win": 0, "pnl": 0.0})
    hours = defaultdict(lambda: {"n": 0, "win": 0, "pnl": 0.0})

    for e in rows:
        if e.get("type") != "fill":
            continue
        pnl = e.get("pnl_pct", 0.0)
        s = sym[e["symbol"]]
        s["n"] += 1
        s["pnl"] += pnl
        s["win"] += 1 if pnl > 0 else 0
        hr = dt.datetime.utcfromtimestamp(e["ts"]).hour
        h = hours[hr]
        h["n"] += 1
        h["pnl"] += pnl
        h["win"] += 1 if pnl > 0 else 0

    def fmt(d):
        return {
            k: {
                "n": v["n"],
                "win%": round(100 * v["win"] / max(1, v["n"]), 1),
                "pnl%": round(v["pnl"] * 100, 2),
            }
            for k, v in d.items()
        }

    return {"symbols": fmt(sym), "hours": fmt(hours)}


if __name__ == "__main__":
    rows = load_mem()
    stats = summarize(rows)
    print("\n=== SYMBOL STATS ===")
    for k, v in stats["symbols"].items():
        print(k, v)
    print("\n=== HOUR STATS (UTC) ===")
    for k, v in sorted(stats["hours"].items()):
        print(k, v)
