"""Curated default news feeds and crawl seeds used by the opt-in pipeline.

This file lists safe, public RSS feeds and a conservative set of crawl seed URLs.
The pipeline uses these defaults unless overridden via environment variables.
"""

from __future__ import annotations

from typing import List

# Public RSS feeds (finance, crypto, tech)
NEWS_FEEDS: List[str] = [
    "https://news.ycombinator.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://www.reuters.com/technology/feed/",
    "https://cointelegraph.com/rss",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://www.forexfactory.com/rss.php",
    "https://www.investing.com/rss/news.rss",
]

# Conservative crawl seeds (educational and public market commentary pages).
# These are used only when ENABLE_CRAWL=true and the crawler is available.
DEFAULT_CRAWL_SEEDS: List[str] = [
    "https://www.investopedia.com/",
    "https://www.forexfactory.com/",
    "https://www.fxstreet.com/",
    "https://www.tradingview.com/ideas/",
    "https://www.coindesk.com/",
    "https://www.reuters.com/",
]

__all__ = ["NEWS_FEEDS", "DEFAULT_CRAWL_SEEDS"]
