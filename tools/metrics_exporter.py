"""Simple metrics exporter for runtime metrics.
Writes runtime/metrics.json every N seconds with counts parsed from logs and paper state.
"""

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "runtime" / "logs" / "continuous_demo.log"
METRICS = ROOT / "runtime" / "metrics.json"
PAPER = ROOT / "runtime" / "paper_state.json"


def read_tail_count(path, needle):
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return 0
    return text.count(needle)


def read_cash():
    try:
        j = json.loads(PAPER.read_text(encoding="utf-8"))
        return float(j.get("cash", 0.0))
    except Exception:
        return 0.0


def main(interval=10):
    METRICS.parent.mkdir(parents=True, exist_ok=True)
    while True:
        ticks = read_tail_count(LOG, "continuous demo tick")
        dryrun_skips = read_tail_count(LOG, "ENABLE_LIVE not true")
        cash = read_cash()
        payload = {
            "ts": int(time.time()),
            "ticks": ticks,
            "dryrun_skips": dryrun_skips,
            "cash": cash,
        }
        try:
            METRICS.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass
        time.sleep(interval)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--interval", type=int, default=10)
    p.add_argument("--once", action="store_true", help="write metrics once and exit")
    args = p.parse_args()
    if args.once:
        # single-shot write for CI/local verification
        ticks = read_tail_count(LOG, "continuous demo tick")
        dryrun_skips = read_tail_count(LOG, "ENABLE_LIVE not true")
        cash = read_cash()
        payload = {
            "ts": int(time.time()),
            "ticks": ticks,
            "dryrun_skips": dryrun_skips,
            "cash": cash,
        }
        METRICS.parent.mkdir(parents=True, exist_ok=True)
        METRICS.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print("metrics written to", METRICS)
    else:
        main(args.interval)
