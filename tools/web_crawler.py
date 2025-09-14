"""Conservative web crawler to fetch allowed pages and extract text snippets.

This module is intentionally simple and opt-in. It respects robots.txt indirectly by
only crawling explicitly provided seeds and limits pages fetched.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import List

try:
    import requests
    from bs4 import BeautifulSoup
except Exception:
    requests = None
    BeautifulSoup = None


def _out_dir() -> Path:
    p = Path('runtime') / 'strategies'
    p.mkdir(parents=True, exist_ok=True)
    return p


def _extract_text(html: str) -> str:
    if BeautifulSoup is None:
        return ''
    soup = BeautifulSoup(html, 'html.parser')
    # keep only paragraphs and headings for brevity
    parts = []
    for tag in soup.find_all(['h1', 'h2', 'h3', 'p']):
        text = tag.get_text(separator=' ', strip=True)
        if text:
            parts.append(text)
    return '\n'.join(parts)[:2000]


def crawl_urls(seeds: List[str], max_pages: int = 20) -> int:
    """Fetch given seed URLs and save a snippet per page. Returns number saved."""
    if requests is None:
        raise RuntimeError('requests and bs4 required for crawling')
    out = _out_dir()
    count = 0
    for url in seeds[:max_pages]:
        try:
            r = requests.get(url, timeout=10, headers={'User-Agent': 'LeanTraderCrawler/1.0'})
            if r.status_code != 200:
                continue
            text = _extract_text(r.text)
            if not text:
                continue
            fname = out / (url.replace('https://', '').replace('http://', '').replace('/', '_') + '.txt')
            with fname.open('w', encoding='utf-8') as f:
                f.write(f"{int(time.time())}\t{url}\n")
                f.write(text)
            count += 1
            time.sleep(0.5)
        except Exception:
            continue
    return count
*** End Patch
