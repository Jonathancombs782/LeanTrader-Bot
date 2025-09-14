"""Diagnostic helper for crawler: prints module availability and runs one crawl."""

from __future__ import annotations

import importlib
import os
import sys
import traceback

# ensure project root is on sys.path so `import tools...` works when run
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)


def check_mod(name: str):
    try:
        m = importlib.import_module(name)
        v = getattr(m, "__version__", None)
        print(f"OK: {name} (version={v})")
        return True
    except Exception as e:
        print(f"MISSING: {name} -> {e}")
        return False


def main():
    print("Python:", sys.version.splitlines()[0])
    for mod in ("requests", "bs4", "tools.web_crawler"):
        check_mod(mod)

    try:
        from tools.web_crawler import crawl_urls

        print("Calling crawl_urls on https://www.investopedia.com/")
        n = crawl_urls(["https://www.investopedia.com/"], max_pages=1)
        print("crawl returned:", n)
    except Exception:
        print("crawl exception:")
        traceback.print_exc()


if __name__ == "__main__":
    main()
