"""Simple RSS news ingester.

This module fetches RSS/Atom feeds via `feedparser` when available and stores
recent items under `runtime/news/` for use by strategies. It is intentionally
opt-in and conservative.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List

try:
    import feedparser  # type: ignore
except Exception:
    feedparser = None


def _ensure_dir() -> Path:
    p = Path("runtime") / "news"
    p.mkdir(parents=True, exist_ok=True)
    return p


def fetch_feeds(urls: List[str], max_items: int = 50) -> int:
    if feedparser is None:
        raise RuntimeError("feedparser required for news ingestion")
    dirp = _ensure_dir()
    count = 0
    for url in urls:
        try:
            d = feedparser.parse(url)
            fname = dirp / (url.replace("https://", "").replace("http://", "").replace("/", "_") + ".ndjson")
            with fname.open("a", encoding="utf-8") as f:
                for e in (d.entries or [])[:max_items]:
                    ts = int(time.time())
                    title = getattr(e, "title", "")
                    link = getattr(e, "link", "")
                    summary = getattr(e, "summary", "")
                    line = f"{ts}\t{title}\t{link}\t{summary}\n"
                    f.write(line)
                    count += 1
        except Exception:
            continue
    return count
