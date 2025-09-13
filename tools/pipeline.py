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

# ensure project root is on sys.path so 'tools' package imports work when
# the script is executed directly (python tools/pipeline.py)
proj_root = Path(__file__).resolve().parents[1]
if str(proj_root) not in sys.path:
    sys.path.insert(0, str(proj_root))

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

    try:
        # prefer absolute imports from the local package
        from tools.evaluate_model import evaluate
        from tools.market_data import fetch_ohlcv
        from tools.news_ingest import fetch_feeds
        from tools.trainer import train_dummy_classifier

        try:
            from tools.web_crawler import crawl_urls
        except Exception:
            crawl_urls = None
    except Exception as e:
        print("pipeline import error", e)
        sys.exit(2)


def _env_true(k: str) -> bool:
    return os.getenv(k, "").strip().lower() in ("1", "true", "yes", "y", "on")


def run_pipeline():
    if not _env_true("ENABLE_LEARNING"):
        print("ENABLE_LEARNING not set; exiting without action")
        return 0

    # simple file lock to avoid concurrent pipeline runs
    lock_file = Path("runtime") / "pipeline.lock"
    try:
        if lock_file.exists():
            print("pipeline already running (lock present); exiting")
            return 0
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        lock_file.write_text(str(os.getpid()))
    except Exception as e:
        print("failed to acquire pipeline lock:", e)
        return 1

    # ensure lock file is cleaned up at process exit even on exceptions
    try:
        import atexit  # local import to avoid global side effects

        def _release_lock() -> None:
            try:
                if lock_file.exists():
                    lock_file.unlink()
            except Exception:
                pass

        atexit.register(_release_lock)
    except Exception:
        pass

    # 1) News ingestion (opt-in feeds). Use curated defaults unless overridden.
    try:
        from .learning_sources import DEFAULT_CRAWL_SEEDS, NEWS_FEEDS  # type: ignore
    except Exception:
        NEWS_FEEDS = [
            "https://news.ycombinator.com/rss",
            "https://www.coindesk.com/arc/outboundfeeds/rss/",
            "https://www.reuters.com/technology/feed/",
        ]
        DEFAULT_CRAWL_SEEDS = []

    feeds_env = os.getenv("LEARNING_FEEDS")
    feeds: List[str] = [s.strip() for s in feeds_env.split(",") if s.strip()] if feeds_env else NEWS_FEEDS
    try:
        print("fetching news feeds...")
        ncount = fetch_feeds(feeds, max_items=10)
        print("news items stored:", ncount)
    except Exception as e:
        print("news ingest failed:", e)

    # optional web crawling of approved pages for strategy snippets
    if _env_true("ENABLE_CRAWL") and crawl_urls is not None:
        try:
            print("running web crawler (ENABLE_CRAWL=true)")
            seeds_env = os.getenv("CRAWL_SEEDS")
            if seeds_env:
                seeds = [s.strip() for s in seeds_env.split(",") if s.strip()]
            else:
                seeds = DEFAULT_CRAWL_SEEDS
            if seeds:
                ccount = crawl_urls(seeds, max_pages=20)
                print("crawler saved snippets:", ccount)
            else:
                print("no CRAWL_SEEDS provided; skipping crawler")
        except Exception as e:
            print("crawler failed:", e)

    # Optional Reddit ingestion via RSS
    if os.getenv("ENABLE_REDDIT_INGEST", "false").strip().lower() in ("1", "true", "yes", "on"):
        try:
            from tools.reddit_ingest import ingest as reddit_ingest

            print("reddit ingest enabled; fetching...")
            rc = reddit_ingest()
            print("reddit items stored:", rc)
        except Exception as e:
            print("reddit ingest failed:", e)

    # Optional Twitter/X ingestion
    if os.getenv("ENABLE_TWITTER_INGEST", "false").strip().lower() in ("1", "true", "yes", "on"):
        try:
            from tools.twitter_ingest import ingest_once as twitter_ingest_once

            print("twitter ingest enabled; fetching...")
            rc = twitter_ingest_once()
            print("twitter items stored:", rc)
        except Exception as e:
            print("twitter ingest failed:", e)

    # Optional Telegram ingestion
    if os.getenv("ENABLE_TELEGRAM_INGEST", "false").strip().lower() in ("1", "true", "yes", "on"):
        try:
            from tools.telegram_ingest import ingest_once as telegram_ingest_once

            print("telegram ingest enabled; fetching...")
            rc = telegram_ingest_once()
            print("telegram items stored:", rc)
        except Exception as e:
            print("telegram ingest failed:", e)

    # 2) Market data fetch
    # Support multiple markets/symbols/timeframes via env lists
    ex = os.getenv("LEARNING_EXCHANGE", "okx").strip()
    syms_env = os.getenv("LEARNING_SYMBOLS", os.getenv("LEARNING_SYMBOL", "BTC/USDT")).strip()
    fx_syms_env = os.getenv("LEARNING_FX_SYMBOLS", "EURUSD,GBPUSD").strip()
    crypto_syms_env = os.getenv("LEARNING_CRYPTO_SYMBOLS", syms_env).strip()
    tfs_env = os.getenv("LEARNING_TFS", os.getenv("LEARNING_TIMEFRAME", "1m,5m,15m,1h,4h")).strip()
    markets_env = os.getenv("LEARNING_MARKETS", "crypto,fx").strip().lower()

    def _csv(x: str) -> List[str]:
        return [s.strip() for s in (x or "").split(",") if s.strip()]

    markets = _csv(markets_env)
    crypto_syms = _csv(crypto_syms_env) if "crypto" in markets else []
    fx_syms = _csv(fx_syms_env) if "fx" in markets else []
    tfs = _csv(tfs_env)

    fetched_any = False
    for sym in crypto_syms:
        for tf in tfs:
            try:
                print(f"fetching OHLCV from {ex} {sym} ({tf}, limit=200)")
                rows = fetch_ohlcv(ex, sym, timeframe=tf, limit=200)
                if rows:
                    fetched_any = True
                    print("fetched rows:", len(rows))
                else:
                    print("no rows fetched")
            except Exception as e:
                print("ohlcv fetch failed:", e)
    # FX via MT5 or oanda/yfinance not handled here; leave a hook for future
    # FX via MT5 fetcher (opt-in)
    fx_csv_ready = False
    if os.getenv("ENABLE_FX_LEARNING_MT5", "false").strip().lower() in ("1", "true", "yes", "on"):
        try:
            from tools.fx_fetcher_mt5 import init_mt5, fetch_fx, save_csv

            if init_mt5():
                for sym in fx_syms:
                    for tf in tfs:
                        if tf.upper() not in ("M1", "M5", "M15", "M30", "H1", "H4", "D1"):
                            continue
                        try:
                            rows = fetch_fx(sym, tf.upper(), 400)
                            if rows:
                                save_csv(sym, tf.upper(), rows)
                                print(f"fx saved {sym} {tf} rows={len(rows)}")
                                fx_csv_ready = True
                        except Exception:
                            pass
            else:
                print("MT5 init failed; skipping FX learning via MT5")
        except Exception as e:
            print("fx mt5 fetch failed:", e)
    # Fallback: OANDA
    if (not fx_csv_ready) and os.getenv("ENABLE_FX_LEARNING_OANDA", "false").strip().lower() in ("1", "true", "yes", "on"):
        try:
            from tools.fx_fetcher_oanda import fetch_fx_full as fetch_fx_oa_full, save_csv as save_csv_oa

            for sym in fx_syms:
                # OANDA instrument format uses underscore
                sym_oa = sym.replace("/", "_") if "/" in sym else sym
                for tf in tfs:
                    tf_up = tf.upper()
                    if tf_up not in ("M1", "M5", "M15", "M30", "H1", "H4", "D1"):
                        continue
                    try:
                        rows = fetch_fx_oa_full(sym_oa, tf_up, 2000)
                        if rows:
                            save_csv_oa(sym, tf_up, rows)
                            print(f"fx(oanda) saved {sym} {tf_up} rows={len(rows)}")
                    except Exception:
                        pass
        except Exception as e:
            print("fx oanda fetch failed:", e)

    # 3) Train on CSV produced by market_data.fetch_ohlcv (persisted at runtime/data)
    # 3) Train + evaluate for every fetched crypto CSV
    data_dir = Path("runtime") / "data"
    any_trained = False
    for tf in tfs:
        for sym in crypto_syms:
            csv_path = data_dir / f"{ex}_{sym.replace('/', '_')}_{tf}.csv"
            if not csv_path.exists():
                continue
            try:
                print("training model from", csv_path)
                out = train_dummy_classifier(str(csv_path))
                print("training output:", out)
                any_trained = True
            except Exception as e:
                print("training failed:", e)
                continue

            # Evaluate
            model_path = out.get("model_path")
            try:
                print("evaluating model", model_path)
                ev = evaluate(model_path, str(csv_path))
                print("evaluation result:", ev)
            except Exception as e:
                print("evaluation failed:", e)

    # Train on FX CSVs (fx_SYM_TF.csv) when present
    for tf in tfs:
        for sym in fx_syms:
            csv_path = data_dir / f"fx_{sym}_{tf.upper()}.csv"
            if not csv_path.exists():
                continue
            try:
                print("training model from", csv_path)
                out = train_dummy_classifier(str(csv_path))
                print("training output:", out)
                any_trained = True
            except Exception as e:
                print("training failed:", e)
                continue
            model_path = out.get("model_path")
            try:
                print("evaluating model", model_path)
                ev = evaluate(model_path, str(csv_path))
                print("evaluation result:", ev)
            except Exception as e:
                print("evaluation failed:", e)

    if not fetched_any:
        print("no data fetched; nothing to train")

    return 0


if __name__ == "__main__":
    rc = run_pipeline()
    # ensure flush
    time.sleep(0.01)
    sys.exit(rc)
