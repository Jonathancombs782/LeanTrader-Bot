from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Dict, List

from ..optional_deps import check_or_raise

_SEEN_PATH = os.getenv("NEWS_SEEN_PATH", "runtime/news_seen.json")
_RATE_MS = int(os.getenv("NEWS_RATE_MS", "1000"))


def _load_seen() -> Dict[str, float]:
    try:
        with open(_SEEN_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_seen(d: Dict[str, float]) -> None:
    try:
        os.makedirs(os.path.dirname(_SEEN_PATH), exist_ok=True)
        with open(_SEEN_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass


@dataclass
class NewsItem:
    ts: float
    title: str
    link: str
    source: str


def fetch_rss(urls: List[str]) -> List[NewsItem]:
    # lazy import feedparser
    try:
        import feedparser  # type: ignore
    except Exception:
        check_or_raise("feedparser", False, extra="feedparser")
        return []

    seen = _load_seen()
    out: List[NewsItem] = []
    for u in urls:
        try:
            time.sleep(_RATE_MS / 1000.0)
            d = feedparser.parse(u)
            for e in d.get("entries", [])[:50]:
                link = str(e.get("link") or "")
                if not link or link in seen:
                    continue
                seen[link] = time.time()
                out.append(
                    NewsItem(
                        ts=(
                            float(e.get("published_parsed").tm_timestamp())
                            if hasattr(e.get("published_parsed"), "tm_timestamp")
                            else time.time()
                        ),
                        title=str(e.get("title") or ""),
                        link=link,
                        source=str(d.get("feed", {}).get("title") or "rss"),
                    )
                )
        except Exception:
            continue
    # persist seen compactly
    try:
        # keep last 5k
        keys = sorted(seen, key=seen.get, reverse=True)[:5000]
        slim = {k: seen[k] for k in keys}
        _save_seen(slim)
    except Exception:
        pass
    return out
