"""Small smoke test for the crawler to verify it can fetch a few static pages."""

from __future__ import annotations

import os
import sys

# ensure project root on sys.path
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)

from tools.web_crawler import crawl_urls  # noqa: E402


def main():
    seeds = [
        "https://www.investopedia.com/",
        "https://www.reuters.com/",
        "https://www.coindesk.com/",
    ]
    n = crawl_urls(seeds, max_pages=3)
    print("snippets saved:", n)


if __name__ == "__main__":
    main()
