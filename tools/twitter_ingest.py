"""Conservative Twitter/X ingestion via v2 API (Bearer token).

Environment:
  ENABLE_TWITTER_INGEST=true
  TWITTER_BEARER_TOKEN=...        # required
  TWITTER_QUERY="bitcoin OR crypto lang:en"         # single query
  TWITTER_QUERIES="bitcoin lang:en,forex lang:en"   # multiple queries (comma-separated)
  TWITTER_MAX_RESULTS=50           # 10..100 per request

Writes brief text snippets to runtime/strategies/twitter_<slug>.txt (one file per query).
Per run, dedupes by tweet id within the request set.
"""

from __future__ import annotations

import os
import time
import urllib.parse as _up
from pathlib import Path
from typing import Any, Dict, List, Set

import requests


def _slug(s: str) -> str:
    s = s.strip().lower().replace(" ", "_")
    return "".join(ch for ch in s if ch.isalnum() or ch in ("_", "-"))[:60]


def _sleep(ms: int) -> None:
    try:
        import time as _t

        _t.sleep(max(0.0, ms) / 1000.0)
    except Exception:
        pass


def _ingest_query(bearer: str, query: str, max_results: int, pages: int, sleep_ms: int) -> int:
    query = query.strip()
    if not query:
        return 0
    bearer = os.getenv("TWITTER_BEARER_TOKEN", "").strip()
    if not bearer:
        return 0
    max_results = min(100, max(10, int(max_results)))
    url = (
        "https://api.twitter.com/2/tweets/search/recent?" + _up.urlencode({"query": query, "max_results": max_results})
    )
    headers = {"Authorization": f"Bearer {bearer}"}
    try:
        seen: Set[str] = set()
        lines: List[str] = []
        next_token = None
        page = 0
        while page < max(1, pages):
            params = {"query": query, "max_results": max_results}
            if next_token:
                params["next_token"] = next_token
            r = requests.get("https://api.twitter.com/2/tweets/search/recent", headers=headers, params=params, timeout=12)
            if r.status_code != 200:
                break
            j = r.json()
            data = j.get("data") or []
            if not data:
                break
            for t in data:
                tid = str(t.get("id", ""))
                if tid in seen:
                    continue
                seen.add(tid)
                txt = str(t.get("text", "")).strip()
                if txt:
                    lines.append("- " + txt)
            meta = j.get("meta", {})
            next_token = meta.get("next_token")
            page += 1
            if not next_token:
                break
            _sleep(sleep_ms)
        if not lines:
            return 0
        outdir = Path("runtime") / "strategies"
        outdir.mkdir(parents=True, exist_ok=True)
        fname = outdir / ("twitter_" + _slug(query) + ".txt")
        with fname.open("w", encoding="utf-8") as f:
            f.write(f"# twitter query: {query} {int(time.time())}\n\n")
            f.write("\n\n".join(lines))
        return len(lines)
    except Exception:
        return 0


def ingest_once() -> int:
    bearer = os.getenv("TWITTER_BEARER_TOKEN", "").strip()
    if not bearer:
        return 0
    q_single = os.getenv("TWITTER_QUERY", "").strip()
    queries_env = os.getenv("TWITTER_QUERIES", "").strip()
    max_results = int(os.getenv("TWITTER_MAX_RESULTS", "50"))
    pages = int(os.getenv("TWITTER_PAGES", "2"))
    sleep_ms = int(os.getenv("TWITTER_SLEEP_MS", "800"))
    queries: List[str] = []
    if queries_env:
        queries = [q.strip() for q in queries_env.split(",") if q.strip()]
    elif q_single:
        queries = [q_single]
    else:
        queries = ["bitcoin OR crypto lang:en"]
    total = 0
    for q in queries:
        total += _ingest_query(bearer, q, max_results, pages, sleep_ms)
    # Lists ingestion
    list_ids_env = os.getenv("TWITTER_LIST_IDS", "").strip()
    if list_ids_env:
        headers = {"Authorization": f"Bearer {bearer}"}
        for lid in [x.strip() for x in list_ids_env.split(",") if x.strip()]:
            try:
                seen: Set[str] = set()
                lines: List[str] = []
                next_token = None
                page = 0
                while page < max(1, pages):
                    params = {"max_results": max_results}
                    if next_token:
                        params["pagination_token"] = next_token
                    r = requests.get(f"https://api.twitter.com/2/lists/{lid}/tweets", headers=headers, params=params, timeout=12)
                    if r.status_code != 200:
                        break
                    j = r.json()
                    data = j.get("data") or []
                    if not data:
                        break
                    for t in data:
                        tid = str(t.get("id", ""))
                        if tid in seen:
                            continue
                        seen.add(tid)
                        txt = str(t.get("text", "")).strip()
                        if txt:
                            lines.append("- " + txt)
                    meta = j.get("meta", {})
                    next_token = meta.get("next_token") or meta.get("previous_token")
                    page += 1
                    if not next_token:
                        break
                    _sleep(sleep_ms)
                if lines:
                    outdir = Path("runtime") / "strategies"
                    outdir.mkdir(parents=True, exist_ok=True)
                    fname = outdir / (f"twitter_list_{lid}.txt")
                    with fname.open("w", encoding="utf-8") as f:
                        f.write(f"# twitter list: {lid} {int(time.time())}\n\n")
                        f.write("\n\n".join(lines))
                    total += len(lines)
            except Exception:
                continue
    return total


if __name__ == "__main__":
    n = ingest_once()
    print("twitter items stored:", n)
