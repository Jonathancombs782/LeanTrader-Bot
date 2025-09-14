"""Conservative Reddit ingestion via public RSS feeds (no API keys required).

Environment:
  REDDIT_SUBS="CryptoCurrency,Bitcoin,Forex"
  REDDIT_MAX_ITEMS=25

Writes brief text snippets to runtime/strategies/
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import List

import feedparser  # type: ignore


def _csv(x: str) -> List[str]:
    return [s.strip() for s in (x or "").split(",") if s.strip()]


def ingest() -> int:
    subs = _csv(os.getenv("REDDIT_SUBS", ""))
    if not subs:
        return 0
    max_items = int(os.getenv("REDDIT_MAX_ITEMS", "25"))
    outdir = Path("runtime") / "strategies"
    outdir.mkdir(parents=True, exist_ok=True)
    count = 0
    for sub in subs:
        url = f"https://www.reddit.com/r/{sub}/.rss"
        try:
            feed = feedparser.parse(url)
            parts: List[str] = []
            for e in (feed.entries or [])[:max_items]:
                title = getattr(e, "title", "").strip()
                summary = getattr(e, "summary", "")
                parts.append(f"- {title}\n{summary}\n")
            if parts:
                fname = outdir / (f"reddit_{sub}.txt")
                with fname.open("w", encoding="utf-8") as f:
                    f.write(f"# reddit r/{sub} {int(time.time())}\n\n")
                    f.write("\n".join(parts))
                count += len(parts)
        except Exception:
            continue
    return count


if __name__ == "__main__":
    n = ingest()
    print("reddit items saved:", n)

