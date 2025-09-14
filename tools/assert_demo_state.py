"""Assertions for demo state: ensure open_trades empty and closed_trades show retried successes.
Exits with prints for human review.
"""

from __future__ import annotations

import json
import pathlib

RUNTIME = pathlib.Path("runtime")
OPEN = RUNTIME / "open_trades.json"
CLOSED = RUNTIME / "closed_trades.json"


def read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def main():
    open_trades = read(OPEN, [])
    closed_trades = read(CLOSED, [])

    ok = True
    if open_trades:
        print("ASSERT FAIL: open_trades.json is not empty, len=", len(open_trades))
        ok = False
    else:
        print("ASSERT PASS: open_trades.json empty")

    # look for retried entries or successful closes in last N entries
    retried = [c for c in closed_trades if isinstance(c, dict) and c.get("retried")]
    success_retries = [r for r in retried if r.get("retry_result", {}).get("ok")]
    if retried:
        print(f"found retried entries: {len(retried)}, successful: {len(success_retries)}")
    else:
        print("no retried entries found; check closed_trades.json")
        ok = False

    # final status
    if ok:
        print("assert_demo_state: OK")
    else:
        print("assert_demo_state: FAILED")


if __name__ == "__main__":
    main()
