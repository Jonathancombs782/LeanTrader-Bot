#!/usr/bin/env python
"""Publish scan or signal events to Redis channels.

Usage:
  python tools/redis_publish.py scan --pairs XAUUSD,EURUSD --post --preview
  python tools/redis_publish.py signal --symbol XAUUSD --side buy --conf 0.8 --id manual-1

Env:
  REDIS_URL                 (e.g., redis://localhost:6379/0)
  SCHEDULER_REDIS_CHANNEL   (default: lt:scan)
  SIGNAL_REDIS_CHANNEL      (default: lt:signal)
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def _redis():
    try:
        import redis  # type: ignore

        url = os.getenv("REDIS_URL")
        if not url:
            print("REDIS_URL not set", file=sys.stderr)
            sys.exit(2)
        return redis.StrictRedis.from_url(url)
    except Exception as e:
        print("redis import/connection failed:", e, file=sys.stderr)
        sys.exit(2)


def pub_scan(args):
    r = _redis()
    chan = os.getenv("SCHEDULER_REDIS_CHANNEL", "lt:scan")
    payload = {
        "cmd": "scan",
        "pairs": args.pairs,
        "post": bool(args.post),
        "preview": bool(args.preview),
    }
    r.publish(chan, json.dumps(payload))
    print("published scan:", chan, payload)


def pub_signal(args):
    r = _redis()
    chan = os.getenv("SIGNAL_REDIS_CHANNEL", "lt:signal")
    payload = {
        "symbol": args.symbol,
        "side": args.side,
        "confidence": float(args.conf),
        "id": args.id or "manual",
    }
    r.publish(chan, json.dumps(payload))
    print("published signal:", chan, payload)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("scan")
    p1.add_argument("--pairs", default=os.getenv("SCAN_PAIRS", "XAUUSD"))
    p1.add_argument("--post", action="store_true")
    p1.add_argument("--preview", action="store_true")
    p1.set_defaults(func=pub_scan)

    p2 = sub.add_parser("signal")
    p2.add_argument("--symbol", required=True)
    p2.add_argument("--side", required=True, choices=["buy", "sell", "hold"])
    p2.add_argument("--conf", default="0.5")
    p2.add_argument("--id", default="")
    p2.set_defaults(func=pub_signal)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
