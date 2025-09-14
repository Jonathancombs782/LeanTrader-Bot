#!/usr/bin/env python3
"""Dry-run monitor: snapshot paper state and demo logs, sleep, then summarize.

Usage: python tools/dryrun_monitor.py --minutes 30
Writes runtime/monitor_summary_<start_ts>.json
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path


def read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def read_log(path: Path):
    try:
        return path.read_text(errors="ignore")
    except Exception:
        return ""


def count_occurrences(text: str, needle: str) -> int:
    return text.count(needle)


def main(minutes: int):
    repo = Path(__file__).resolve().parent.parent
    runtime = repo / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    state_file = runtime / "paper_state.json"
    demo_log = runtime / "logs" / "continuous_demo.log"

    start_ts = int(time.time())
    start_dt = datetime.utcfromtimestamp(start_ts).isoformat() + "Z"

    before_state = read_json(state_file)
    before_log = read_log(demo_log)

    summary = {
        "start_time": start_dt,
        "start_cash": before_state.get("cash"),
        "start_history_len": len(before_state.get("history", [])),
        "start_demo_log_len": len(before_log.splitlines()),
        "start_demo_ticks": count_occurrences(before_log, "continuous demo tick"),
        "start_enable_msgs": count_occurrences(before_log, "ENABLE_LIVE"),
    }

    # Sleep in 60s intervals so it can be interrupted if needed
    total = int(minutes) * 60
    slept = 0
    while slept < total:
        to_sleep = min(60, total - slept)
        time.sleep(to_sleep)
        slept += to_sleep

    end_ts = int(time.time())
    end_dt = datetime.utcfromtimestamp(end_ts).isoformat() + "Z"

    after_state = read_json(state_file)
    after_log = read_log(demo_log)

    summary.update(
        {
            "end_time": end_dt,
            "end_cash": after_state.get("cash"),
            "end_history_len": len(after_state.get("history", [])),
            "end_demo_log_len": len(after_log.splitlines()),
            "end_demo_ticks": count_occurrences(after_log, "continuous demo tick"),
            "end_enable_msgs": count_occurrences(after_log, "ENABLE_LIVE"),
        }
    )

    summary["delta_cash"] = None
    try:
        sc = float(summary.get("start_cash") or 0)
        ec = float(summary.get("end_cash") or 0)
        summary["delta_cash"] = ec - sc
    except Exception:
        pass

    out = runtime / f"monitor_summary_{start_ts}.json"
    out.write_text(json.dumps(summary, indent=2))
    print("monitor finished", out)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--minutes", type=int, default=30)
    args = p.parse_args()
    main(args.minutes)
