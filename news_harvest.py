# news_harvest.py
from __future__ import annotations

import os
import re
import csv
import json
import time
import math
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any

import feedparser  # pip install feedparser

# ---------- Optional Telegram notify ----------
import requests

def _tg_send(text: str) -> None:
    try:
        if os.getenv("TELEGRAM_ENABLED", "false").lower() != "true":
            return
        tok = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat = os.getenv("TELEGRAM_CHAT_ID", "")
        if not tok or not chat:
            return
        url = f"https://api.telegram.org/bot{tok}/sendMessage"
        payload = {"chat_id": chat, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass

# ---------- Logging ----------
LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "news.log"), logging.StreamHandler()],
)
log = logging.getLogger("news_harvest")

# ---------- Data paths ----------
DATA_DIR = Path("data"); DATA_DIR.mkdir(exist_ok=True)
RAW_FILE   = DATA_DIR / "news_raw.csv"   # raw harvested rows (append)
CLEAN_FILE = DATA_DIR / "news.csv"       # cleaned & ranked output
SEEN_FILE  = DATA_DIR / "news_seen.json" # link/title hashes to avoid dupes

# ---------- RSS sources ----------
RSS: List[str] = [
    # Crypto
    "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
    "https://cointelegraph.com/rss",
    "https://www.theblock.co/rss.xml",
    "https://decrypt.co/feed",
    # Macro/FX
    "https://www.forexlive.com/feed/",
    "https://www.fxstreet.com/rss",
    "https://www.investing.com/rss/news_301.rss",   # breaking
    "https://www.investing.com/rss/news_25.rss",    # economic indicators
]

# ---------- NLTK VADER (with auto-download) ----------
VADER_READY = False
try:
    import nltk
    from nltk.sentiment import SentimentIntensityAnalyzer
    try:
        nltk.data.find("sentiment/vader_lexicon.zip")
        VADER_READY = True
    except LookupError:
        nltk.download("vader_lexicon", quiet=True)
        nltk.data.find("sentiment/vader_lexicon.zip")
        VADER_READY = True
except Exception as e:
    log.warning("NLTK/VADER unavailable (%s). Sentiment will be zero.", e)

if VADER_READY:
    SIA = SentimentIntensityAnalyzer()
else:
    SIA = None

# ---------- Impact keywords ----------
IMPACT_WEIGHTS = {
    # Macro/Fed
    r"\b(CPI|PCE|inflation|FOMC|rate hike|rate cut|interest rate|Powell|nonfarm|NFP|unemployment|PPI)\b": 4.0,
    r"\b(ECB|BOE|BOJ|SNB|RBA|RBNZ|rate decision|central bank)\b": 3.5,
    r"\b(GDP|ISM|PMI|retail sales|consumer confidence|housing starts)\b": 2.5,
    # Crypto
    r"\b(ETF|listing|delist|SEC|approval|lawsuit|settlement|hack|exploit|airdrop|halving|upgrade|fork)\b": 4.0,
    r"\b(Bitcoin|BTC|Ethereum|ETH|Solana|SOL|XRP|DOGE|Cardano|ADA)\b": 2.0,
    # General market heat
    r"\b(soar|plunge|surge|crash|spike|tumble|rally|selloff)\b": 2.0,
}

CRYPTO_HINTS = re.compile(r"\b(BTC|ETH|SOL|DOGE|XRP|ADA|crypto|bitcoin|ethereum|solana|defi|exchange|binance|coinbase|token|stablecoin)\b", re.I)
FX_HINTS     = re.compile(r"\b(USD|EUR|GBP|JPY|AUD|NZD|CHF|CAD|forex|FX|pair|pips|yield|treasury)\b", re.I)

def _hash_key(title: str, link: str) -> str:
    return hashlib.sha256((title.strip() + "|" + link.strip()).encode("utf-8")).hexdigest()

def _load_seen() -> set[str]:
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()

def _save_seen(seen: set[str]) -> None:
    try:
        SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")
    except Exception:
        pass

def _parse_time(dt_str: str) -> float:
    """
    Returns UTC epoch seconds. If feed lacks time, use now().
    """
    if not dt_str:
        return time.time()
    try:
        # feedparser may parse published_parsed
        return time.mktime(feedparser._parse_date(dt_str))  # type: ignore
    except Exception:
        try:
            # last resort
            return datetime.fromisoformat(dt_str.replace("Z","")).replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            return time.time()

def _sentiment(text: str) -> float:
    if not SIA:
        return 0.0
    s = SIA.polarity_scores(text)
    # compound in [-1, 1] → rescale to [-1, 1] (already), keep as is
    return float(s.get("compound", 0.0))

def _impact(text: str) -> float:
    t = text.lower()
    score = 0.0
    for pat, w in IMPACT_WEIGHTS.items():
        if re.search(pat, t, re.I):
            score += w
    return score

def _market(text: str) -> str:
    t = text.upper()
    if CRYPTO_HINTS.search(t):
        return "crypto"
    if FX_HINTS.search(t):
        return "fx"
    return "macro"

def _rank_score(sent: float, imp: float, age_min: float) -> float:
    """
    Higher is better. We combine:
      - |sentiment| emphasis (both highly pos/neg can move markets)
      - impact weight
      - freshness (decay with age)
    """
    freshness = math.exp(-age_min / 360.0)  # 6h half-ish life
    return (abs(sent) * 2.0 + imp) * freshness

def harvest_rss() -> int:
    """
    Pull newest items from RSS feeds, de-duplicate (by title+link hash),
    and append to news_raw.csv. Returns number of new rows appended.
    """
    seen = _load_seen()
    new_rows: List[Dict[str, Any]] = []
    now = time.time()

    for url in RSS:
        try:
            d = feedparser.parse(url)
            src = d.feed.get("title", url.split("/")[2]) if hasattr(d, "feed") else url
            entries = getattr(d, "entries", []) or []
            for e in entries[:50]:
                title = e.get("title", "").strip()
                link  = e.get("link", "").strip() or url
                if not title:
                    continue
                key = _hash_key(title, link)
                if key in seen:
                    continue
                published = e.get("published") or e.get("updated") or ""
                ts = _parse_time(published)
                new_rows.append({
                    "time": int(ts),
                    "published": published or "",
                    "source": src,
                    "title": title,
                    "link": link,
                    "summary": (e.get("summary") or e.get("description") or "").strip(),
                })
                seen.add(key)
        except Exception as ex:
            log.warning("RSS parse failed %s: %s", url, ex)

    if not new_rows:
        log.info("No new headlines.")
        return 0

    # Append to RAW_FILE (create if needed)
    file_exists = RAW_FILE.exists()
    with open(RAW_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["time","published","source","title","link","summary"])
        if not file_exists:
            w.writeheader()
        for r in sorted(new_rows, key=lambda x: x["time"], reverse=False):
            w.writerow(r)

    _save_seen(seen)
    log.info("Harvested %d new rows -> %s", len(new_rows), RAW_FILE)
    return len(new_rows)

def build_clean(min_market: str | None = None, horizon_hours: float = 48.0) -> int:
    """
    Read RAW_FILE, compute market, sentiment, impact, score, and write
    a ranked CLEAN_FILE for the last `horizon_hours`.
    Optionally filter by market: 'crypto' | 'fx' | 'macro'
    Returns number of rows written.
    """
    if not RAW_FILE.exists():
        log.warning("No raw file found, creating empty clean file.")
        with open(CLEAN_FILE, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=[
                "time","iso","market","source","title","link","sentiment","impact","score"
            ])
            w.writeheader()
        return 0

    cutoff = time.time() - horizon_hours * 3600.0
    out_rows: List[Dict[str, Any]] = []

    with open(RAW_FILE, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                ts = int(row["time"])
            except Exception:
                continue
            if ts < cutoff:
                continue
            title = row["title"]
            txt = (title + " " + row.get("summary","")).strip()
            market = _market(txt)
            if min_market and market != min_market:
                continue
            sent = _sentiment(txt)
            imp  = _impact(txt)
            age_min = max(1.0, (time.time() - ts) / 60.0)
            score = _rank_score(sent, imp, age_min)
            out_rows.append({
                "time": ts,
                "iso": datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
                "market": market,
                "source": row["source"],
                "title": title,
                "link": row["link"],
                "sentiment": f"{sent:.4f}",
                "impact": f"{imp:.2f}",
                "score": f"{score:.6f}",
            })

    out_rows.sort(key=lambda x: float(x["score"]), reverse=True)

    with open(CLEAN_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "time","iso","market","source","title","link","sentiment","impact","score"
        ])
        w.writeheader()
        w.writerows(out_rows)

    log.info("Built clean file with %d rows -> %s", len(out_rows), CLEAN_FILE)

    # Optional Telegram: post top headlines (score threshold)
    try:
        if os.getenv("TELEGRAM_ENABLED","false").lower() == "true":
            top = [r for r in out_rows[:5] if float(r["score"]) >= 1.5]
            if top:
                lines = ["🗞 *Headlines*"]
                for r in top:
                    lines.append(f"• {r['title']} — _{r['source']}_ ({r['market']})")
                _tg_send("\n".join(lines))
    except Exception:
        pass

    return len(out_rows)

def main():
    added = harvest_rss()
    wrote = build_clean(None)
    print(f"[news] harvested={added}, cleaned_rows={wrote}")

if __name__ == "__main__":
    main()
# news_harvest.py