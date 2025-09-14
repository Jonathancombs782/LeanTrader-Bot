from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Dict, List

import requests


def commits_in_window(owner_repo: str, days: int = 3, token: str | None = None) -> int:
    base = f"https://api.github.com/repos/{owner_repo}/commits"
    since = (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat() + "Z"
    params = {"since": since}
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.get(base, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        return len(r.json())
    except Exception:
        return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Collect recent GitHub commits per repo and write GITHUB_COMMITS_PATH JSON")
    p.add_argument("--repos", required=True, help="comma-separated owner/repo list")
    p.add_argument("--out", default=os.getenv("GITHUB_COMMITS_PATH", "runtime/github_commits.json"))
    p.add_argument("--days", type=int, default=int(os.getenv("GITHUB_COMMITS_DAYS", "3")))
    args = p.parse_args()

    token = os.getenv("GITHUB_TOKEN", "").strip() or None
    repos = [s.strip() for s in args.repos.split(",") if s.strip()]
    out: Dict[str, Dict[str, float]] = {}
    for repo in repos:
        n = commits_in_window(repo, days=args.days, token=token)
        out[repo] = {"value": float(n), "ts": float(dt.datetime.utcnow().timestamp())}

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"count": len(out)}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

