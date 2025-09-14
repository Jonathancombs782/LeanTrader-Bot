# run_crawler.py
"""Run the conservative crawler with a small seed list of sources.

Usage:
    .venv/Scripts/python tools/run_crawler.py

This is intentionally conservative and opt-in.
"""
from __future__ import annotations

import os
import sys

# Ensure the tools package directory is on sys.path when running as a script
HERE = os.path.dirname(__file__)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import crawler  # noqa: E402

# small seed lists (user can edit)
RSS_SOURCES = [
    "https://www.reuters.com/finance/markets/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
]

HTML_SOURCES = [
    # select a few public blogs / forums
    "https://www.reddit.com/r/CryptoCurrency/",
    "https://www.reddit.com/r/Forex/",
]

if __name__ == "__main__":
    print("Fetching RSS...")
    try:
        n = crawler.fetch_rss(RSS_SOURCES, max_items=30)
        print(f"RSS items written: {n}")
    except Exception as e:
        print("RSS fetch failed:", e)
    print("Fetching HTML posts...")
    try:
        n = crawler.fetch_html_posts(HTML_SOURCES, css_selector=".Post, .thing, article", max_items=20)
        print(f"HTML items written: {n}")
    except Exception as e:
        print("HTML fetch failed:", e)
    print("Done. Check runtime/news/")
