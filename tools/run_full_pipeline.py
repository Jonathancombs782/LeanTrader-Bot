"""Explicit full pipeline runner: news -> crawl -> ohlcv -> train -> evaluate.

This script avoids package import quirks by adding the project root to sys.path
and calling the helper functions directly. It prints step-by-step output.
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

# ensure project root on sys.path
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)


def _append_log(line: str) -> None:
    try:
        p = Path("runtime") / "logs" / "full_pipeline_run.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(f"{line}\n")
    except Exception:
        pass


def main():
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print("full pipeline start", ts)
    _append_log(f"full pipeline start {ts}")
    try:
        from tools.evaluate_model import evaluate
        from tools.learning_sources import DEFAULT_CRAWL_SEEDS, NEWS_FEEDS
        from tools.news_ingest import fetch_feeds
        from tools.trainer import train_dummy_classifier
        from tools.web_crawler import crawl_urls
    except Exception as _e:
        print("import error:", _e)
        traceback.print_exc()
        return 2

    # 1) News
    try:
        print("1) fetching news feeds...")
        _append_log("1) fetching news feeds...")
        n = fetch_feeds(NEWS_FEEDS, max_items=10)
        print("  news items fetched:", n)
        _append_log(f"  news items fetched: {n}")
    except Exception as _e:
        print("  news ingest failed:", _e)
        _append_log(f"  news ingest failed: {_e}")

    # 2) Crawl
    try:
        print("2) crawling default seeds...")
        _append_log("2) crawling default seeds...")
        seeds = DEFAULT_CRAWL_SEEDS
        if seeds:
            c = crawl_urls(seeds, max_pages=10)
            print("  crawler saved snippets:", c)
            _append_log(f"  crawler saved snippets: {c}")
        else:
            print("  no default crawl seeds configured")
            _append_log("  no default crawl seeds configured")
    except Exception as _e:
        print("  crawler failed:", _e)
        _append_log(f"  crawler failed: {_e}")

    # 3) OHLCV (try a list of exchanges with fallback)
    try:
        print("3) fetching OHLCV...")
        _append_log("3) fetching OHLCV...")
        # prefer gateio (diagnostic showed gateio OK), then try others
        ex_order = ["gateio", "binance", "kucoin", "bybit", "okx"]
        from tools.market_data import fetch_ohlcv_multi

        used_ex, rows = fetch_ohlcv_multi(ex_order, "BTC/USDT", timeframe="1m", limit=200)
        print("  rows fetched:", len(rows), "from", used_ex)
        _append_log(f"  rows fetched: {len(rows)} from {used_ex}")
    except Exception as _e:
        print("  ohlcv fetch failed:", _e)
        _append_log(f"  ohlcv fetch failed: {_e}")

    # 4) Train
    csv_path = Path("runtime") / "data" / "binance_BTC_USDT_1m.csv"
    if not csv_path.exists():
        print("CSV not found, skipping training")
        _append_log("CSV not found, skipping training")
        return 0
    try:
        print("4) training model from", csv_path)
        _append_log(f"4) training model from {csv_path}")
        out = train_dummy_classifier(str(csv_path))
        print("  training output:", out)
        _append_log(f"  training output: {out}")
    except Exception as _e:
        print("  training failed:", _e)
        _append_log(f"  training failed: {_e}")
        traceback.print_exc()
        return 2

    # 5) Evaluate
    try:
        mp = out.get("model_path")
        print("5) evaluating model", mp)
        _append_log(f"5) evaluating model {mp}")
        ev = evaluate(mp, str(csv_path))
        print("  evaluation:", ev)
        _append_log(f"  evaluation: {ev}")
    except Exception as _e:
        print("  evaluation failed:", _e)
        _append_log(f"  evaluation failed: {_e}")
        traceback.print_exc()

    ts2 = time.strftime("%Y-%m-%d %H:%M:%S")
    print("full pipeline done", ts2)
    _append_log(f"full pipeline done {ts2}")
    return 0


if __name__ == "__main__":
    rc = main()
    sys.exit(rc)
