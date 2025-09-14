Opt-in learning pipeline (news, market data, crawler, trainer)
=============================================================

What this does
--------------
- Conservative, opt-in pipeline that ingests news, fetches OHLCV market data,
  optionally crawls approved pages for strategy snippets, trains a small model,
  and evaluates it locally. It never sends live orders.

Files added
-----------
- `tools/pipeline.py` - main opt-in pipeline (ENABLE_LEARNING)
- `tools/news_ingest.py` - RSS/Atom feed ingestion (feedparser)
- `tools/market_data.py` - ccxt-based OHLCV fetcher (ccxt)
- `tools/web_crawler.py` - small opt-in crawler (requests + bs4)
- `tools/trainer.py` - training scaffold (scikit-learn optional)
- `tools/evaluate_model.py` - evaluate saved models on CSVs
- `tools/model_registry.py` - list models and read metadata
- `tools/schedule_pipeline.ps1` - (optional) register a Windows scheduled task

Key environment controls (safety-first)
-------------------------------------
- `ENABLE_LEARNING` (default false) - must be truthy to run the pipeline.
- `ENABLE_CRAWL` (default false) - enables the crawler portion (opt-in).
- `CRAWL_SEEDS` - comma-separated list of seed URLs used by the crawler.
- `ALLOW_LIVE` / `ENABLE_LIVE` / `LIVE_CONFIRM` - unchanged router safety flags; the pipeline will NOT enable live trading.

How to run (local, safe)
-------------------------
1. Activate your virtualenv and install optional deps if needed:

   pip install -r requirements_fx.txt

2. Run pipeline in paper/safe mode (no live trading):

   # enable the learning pipeline (opt-in)
   $env:ENABLE_LEARNING = 'true'
   python tools\pipeline.py

3. To enable crawling, set seeds and the flag:

   $env:ENABLE_CRAWL = 'true'
   $env:CRAWL_SEEDS = 'https://example.com/article1,https://example.com/guide'
   python tools\pipeline.py

Scheduler (optional)
--------------------
Register the provided scheduled task helper to run the pipeline hourly (opt-in):

   powershell -File tools\schedule_pipeline.ps1

Notes and next steps
--------------------
- The pipeline writes artifacts under `runtime/` (ignored by git). Models are pickled under `runtime/models`.
- The router and runners remain protected by runtime overlays and environment checks; training and crawling never enable or send live orders.
- I recommend monitoring disk usage for `runtime/models` and pruning older models regularly. I can add an automated retention policy.

If you'd like, I will:
- register the scheduled task for you,
- add model retention and monitoring, or
- extend the crawler to respect robots.txt and more advanced scraping controls.
