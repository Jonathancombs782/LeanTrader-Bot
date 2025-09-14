from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Dict, List

import requests


def search_counts(query: str, token: str, minutes: int = 60) -> int:
    # Twitter API v2 recent counts endpoint
    url = "https://api.twitter.com/2/tweets/counts/recent"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"query": query, "granularity": "minute"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        buckets = data.get("data", [])[-minutes:]
        return sum(int(b.get("tweet_count", 0)) for b in buckets)
    except Exception:
        return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Collect Twitter mention rates and write TWITTER_RATES_PATH JSON")
    p.add_argument("--assets", required=True, help="comma-separated asset tickers, e.g., BTC,ETH,SOL")
    p.add_argument("--out", default=os.getenv("TWITTER_RATES_PATH", "runtime/twitter_rates.json"))
    p.add_argument("--minutes", type=int, default=int(os.getenv("TWITTER_WINDOW_MIN", "60")))
    args = p.parse_args()

    token = os.getenv("TW_BEARER", "").strip()
    if not token:
        print(json.dumps({"error": "TW_BEARER missing"}))
        return 2
    assets = [s.strip().upper() for s in args.assets.split(",") if s.strip()]
    out: Dict[str, Dict[str, float]] = {}
    for a in assets:
        q = f"({a} OR #{a}) lang:en -is:retweet"
        n = search_counts(q, token, minutes=args.minutes)
        out[a] = {"value": float(n), "ts": float(dt.datetime.utcnow().timestamp())}

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"count": len(out)}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

