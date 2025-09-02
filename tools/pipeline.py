"""Opt-in pipeline: ingest news -> fetch market data -> train -> evaluate.

This script only performs actions when ENABLE_LEARNING env var is truthy.
It is conservative and does not perform any live trading.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import List

# local helpers
try:
    from news_ingest import fetch_feeds
    from market_data import fetch_ohlcv
    from trainer import train_dummy_classifier
    from evaluate_model import evaluate
    try:
        from web_crawler import crawl_urls
    except Exception:
        crawl_urls = None
except Exception as e:
    print('pipeline import error', e)
    sys.exit(2)


def _env_true(k: str) -> bool:
    return os.getenv(k, '').strip().lower() in ('1', 'true', 'yes', 'y', 'on')


def run_pipeline():
    if not _env_true('ENABLE_LEARNING'):
        print('ENABLE_LEARNING not set; exiting without action')
        return 0

    # simple file lock to avoid concurrent pipeline runs
    lock_file = Path('runtime') / 'pipeline.lock'
    try:
        if lock_file.exists():
            print('pipeline already running (lock present); exiting')
            return 0
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        lock_file.write_text(str(os.getpid()))
    except Exception as e:
        print('failed to acquire pipeline lock:', e)
        return 1

    # 1) News ingestion (opt-in feeds)
    feeds: List[str] = [
        'https://news.ycombinator.com/rss',
        'https://www.coindesk.com/arc/outboundfeeds/rss/',
        'https://www.reuters.com/technology/feed/',
    ]
    try:
        print('fetching news feeds...')
        ncount = fetch_feeds(feeds, max_items=10)
        print('news items stored:', ncount)
    except Exception as e:
        print('news ingest failed:', e)

    # optional web crawling of approved pages for strategy snippets
    if _env_true('ENABLE_CRAWL') and crawl_urls is not None:
        try:
            print('running web crawler (ENABLE_CRAWL=true)')
            seeds = os.getenv('CRAWL_SEEDS', '').split(',') if os.getenv('CRAWL_SEEDS') else []
            seeds = [s.strip() for s in seeds if s.strip()]
            if seeds:
                ccount = crawl_urls(seeds, max_pages=20)
                print('crawler saved snippets:', ccount)
            else:
                print('no CRAWL_SEEDS provided; skipping crawler')
        except Exception as e:
            print('crawler failed:', e)

    # 2) Market data fetch
    try:
        print('fetching OHLCV from binance BTC/USDT (1m, limit=200)')
        rows = fetch_ohlcv('binance', 'BTC/USDT', timeframe='1m', limit=200)
        if rows:
            print('fetched rows:', len(rows))
        else:
            print('no rows fetched')
    except Exception as e:
        print('ohlcv fetch failed:', e)

    # 3) Train on CSV produced by market_data.fetch_ohlcv (persisted at runtime/data)
    csv_path = Path('runtime') / 'data' / 'binance_BTC_USDT_1m.csv'
    if not csv_path.exists():
        print('CSV not found; skipping training')
        return 0

    try:
        print('training model from', csv_path)
        out = train_dummy_classifier(str(csv_path))
        print('training output:', out)
    except Exception as e:
        print('training failed:', e)
        return 2

    # 4) Evaluate newly trained model
    model_path = out.get('model_path')
    try:
        print('evaluating model', model_path)
        ev = evaluate(model_path, str(csv_path))
        print('evaluation result:', ev)
    except Exception as e:
        print('evaluation failed:', e)
    finally:
        try:
            if lock_file.exists():
                lock_file.unlink()
        except Exception:
            pass

    return 0


if __name__ == '__main__':
    rc = run_pipeline()
    # ensure flush
    time.sleep(0.01)
    sys.exit(rc)
