"""Conservative crawler utilities.

Provides:
- fetch_rss(urls)
- fetch_html_posts(urls, css_selector) -> extracts titles/links/snippets
- write entries to runtime/news/

This module is intentionally minimal and opt-in. It does NOT place trades.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List

try:
    import requests
except Exception:
    requests = None

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

try:
    import feedparser
except Exception:
    feedparser = None


def _ensure_dir() -> Path:
    p = Path("runtime") / "news"
    p.mkdir(parents=True, exist_ok=True)
    return p


def fetch_rss(urls: List[str], max_items: int = 50) -> int:
    if feedparser is None:
        raise RuntimeError("feedparser is required: pip install feedparser")
    outdir = _ensure_dir()
    count = 0
    for url in urls:
        try:
            d = feedparser.parse(url)
            fname = outdir / (url.replace("https://", "").replace("http://", "").replace("/", "_") + ".ndjson")
            with fname.open("a", encoding="utf-8") as fh:
                for e in (d.entries or [])[:max_items]:
                    entry = {
                        "ts": int(time.time()),
                        "source": url,
                        "title": getattr(e, "title", ""),
                        "link": getattr(e, "link", ""),
                        "summary": getattr(e, "summary", ""),
                    }
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    count += 1
        except Exception:
            continue
    return count


def fetch_html_posts(urls: List[str], css_selector: str = "article, .post, .entry", max_items: int = 50) -> int:
    """Fetch HTML pages and extract posts using a CSS selector. Conservative extractor.

    Returns number of items written.
    """
    if requests is None or BeautifulSoup is None:
        raise RuntimeError("requests and beautifulsoup4 are required: pip install requests beautifulsoup4")
    outdir = _ensure_dir()
    count = 0
    for url in urls:
        try:
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            nodes = soup.select(css_selector)
            fname = outdir / (url.replace("https://", "").replace("http://", "").replace("/", "_") + ".ndjson")
            with fname.open("a", encoding="utf-8") as fh:
                for n in nodes[:max_items]:
                    title = n.find("h1") or n.find("h2") or n.find("a")
                    title_text = title.get_text(strip=True) if title else (n.get_text(strip=True)[:120])
                    link = ""
                    a = n.find("a")
                    if a and a.get("href"):
                        link = a.get("href")
                    snippet = n.get_text(separator=" ", strip=True)[:800]
                    entry = {
                        "ts": int(time.time()),
                        "source": url,
                        "title": title_text,
                        "link": link,
                        "summary": snippet,
                    }
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    count += 1
        except Exception:
            continue
    return count


def list_sources() -> Dict[str, int]:
    p = _ensure_dir()
    out = {}
    for f in p.glob("*.ndjson"):
        out[f.name] = f.stat().st_size
    return out
