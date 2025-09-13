from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import requests


def main() -> int:
    p = argparse.ArgumentParser(description="Post ideas Slack payload if SLACK_WEBHOOK_URL is set")
    p.add_argument("--payload", default=os.getenv("IDEAS_SLACK_FILE", "runtime/ideas_slack.json"))
    args = p.parse_args()

    url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not url:
        print("no SLACK_WEBHOOK_URL; skipping")
        return 0
    data = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    r = requests.post(url, json=data, timeout=15)
    print("posted", r.status_code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

