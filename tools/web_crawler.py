"""Conservative web crawler to fetch allowed pages and extract text snippets.

This module is intentionally simple and opt-in. It respects robots.txt indirectly by
only crawling explicitly provided seeds and limits pages fetched.
"""
from __future__ import annotations

import time
import traceback
from pathlib import Path
from typing import List
from urllib.parse import urlparse

try:
    import requests
    from bs4 import BeautifulSoup
    from urllib import robotparser
except Exception:
    requests = None
    BeautifulSoup = None
    robotparser = None


def _out_dir() -> Path:
    p = Path('runtime') / 'strategies'
    p.mkdir(parents=True, exist_ok=True)
    return p


def _log_dir() -> Path:
    p = Path('runtime') / 'logs'
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


def _write_log(line: str) -> None:
    try:
        p = _log_dir() / 'crawler.log'
        with p.open('a', encoding='utf-8') as f:
            f.write(f"{int(time.time())}\t{line}\n")
    except Exception:
        pass


def crawl_urls(seeds: List[str], max_pages: int = 20, retries: int = 3) -> int:
    """Fetch given seed URLs and save a snippet per page. Returns number saved.

    Adds simple logging and retries for network robustness.
    """
    if requests is None or robotparser is None:
        raise RuntimeError('requests, beautifulsoup4 and urllib.robotparser required for crawling')
    out = _out_dir()
    count = 0
    session = requests.Session()
    session.headers.update({'User-Agent': 'LeanTraderCrawler/1.0'})
    for url in seeds[:max_pages]:
        # check robots.txt for the domain
        try:
            parsed = urlparse(url)
            rp = robotparser.RobotFileParser()
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            rp.set_url(robots_url)
            rp.read()
            if not rp.can_fetch(session.headers['User-Agent'], url):
                _write_log(f"ROBOTS_DENY\t{url}")
                continue
            # respect Crawl-delay if provided (not all robots.txt include it)
            crawl_delay = rp.crawl_delay(session.headers['User-Agent']) or 0
        except Exception:
            crawl_delay = 0
        if crawl_delay:
            _write_log(f"CRAWL_DELAY\t{url}\tdelay={crawl_delay}")
        attempt = 0
        success = False
        while attempt < retries and not success:
            attempt += 1
            try:
                r = session.get(url, timeout=10)
                _write_log(f"FETCH\t{url}\tstatus={r.status_code}\tattempt={attempt}")
                if r.status_code != 200:
                    time.sleep(0.5 * attempt)
                    continue
                text = _extract_text(r.text)
                if not text:
                    _write_log(f"NO_TEXT\t{url}\tattempt={attempt}")
                    break
                safe_name = url.replace('https://', '').replace('http://', '').replace('/', '_')
                fname = out / (safe_name + '.txt')
                with fname.open('w', encoding='utf-8') as f:
                    f.write(f"{int(time.time())}\t{url}\n")
                    f.write(text)
                count += 1
                success = True
                # polite pause between requests
                time.sleep(max(0.5, float(crawl_delay)))
            except Exception as e:
                _write_log(f"ERROR\t{url}\tattempt={attempt}\terror={str(e)}")
                _write_log(traceback.format_exc())
                time.sleep(0.5 * attempt)
        if not success:
            _write_log(f"FAILED\t{url}\tretries={retries}")
    return count
