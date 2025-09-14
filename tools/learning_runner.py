"""Orchestrator: run crawl, fetch data, train models, and run a paper-mode simulation."""

from __future__ import annotations

import time
import traceback
from pathlib import Path

from tools.ensemble_trainer import train_ensemble_from_dir
from tools.learning_sources import DEFAULT_CRAWL_SEEDS, NEWS_FEEDS
from tools.market_data import fetch_ohlcv_multi
from tools.news_ingest import fetch_feeds
from tools.web_crawler import crawl_urls


def _write(lines: list[str], fname: str) -> None:
    p = Path("runtime") / "logs" / fname
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def main() -> int:
    lines = []
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"learning_runner start {ts}")
    try:
        # 1) news
        n = fetch_feeds(NEWS_FEEDS, max_items=50)
        lines.append(f"news fetched: {n}")
        # 2) crawl
        c = crawl_urls(DEFAULT_CRAWL_SEEDS, max_pages=50)
        lines.append(f"crawl snippets: {c}")
        # 3) fetch ohlcv (attempt multi-exchange)
        ex_order = ["gateio", "binance", "kucoin", "bybit", "okx"]
        try:
            used, rows = fetch_ohlcv_multi(ex_order, "BTC/USDT", timeframe="1m", limit=500)
            lines.append(f"ohlcv fetched from {used}: rows={len(rows)}")
        except Exception as e:
            lines.append(f"ohlcv fetch failed: {e}")
        # 4) train
        try:
            out = train_ensemble_from_dir("runtime/data")
            lines.append(f"trained models: {out.get('models')}")
        except Exception as e:
            lines.append(f"training failed: {e}")

    except Exception as e:
        lines.append(f"learning runner outer failure: {e}")
        lines.append(traceback.format_exc())

    ts2 = time.strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"learning_runner done {ts2}")
    _write(lines, "learning_runner.txt")
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
