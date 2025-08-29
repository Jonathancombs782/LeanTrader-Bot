# geo.py
from __future__ import annotations
import os, json, time, socket, sys
from typing import List
import requests

# --- simple, robust geo detection ---
def detect_country() -> str:
    """
    Return ISO-2 country code, e.g. 'US', 'NG', 'GB'.
    Order: env override -> ipapi.co -> ipinfo.io -> fallback 'US'
    """
    cc = (os.getenv("GEO_COUNTRY") or os.getenv("COUNTRY") or "").strip().upper()
    if cc: return cc
    for url in ("https://ipapi.co/json", "https://ipinfo.io/json"):
        try:
            r = requests.get(url, timeout=4)
            j = r.json()
            for key in ("country", "countryCode"):
                if key in j and j[key]:
                    return str(j[key]).strip().upper()
        except Exception:
            pass
    return "US"

# --- regional news feeds (you can merge into news_service if you prefer) ---
REGIONAL_FEEDS = {
    "DEFAULT": [
        "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
        "https://cointelegraph.com/rss",
        "https://www.theblock.co/rss",
        "https://www.forexlive.com/feed/",
        "https://www.fxstreet.com/rss",
        "https://www.marketwatch.com/feeds/topstories",
        "https://www.reuters.com/markets/feeds/rss",
    ],
    "US": [
        "https://www.marketwatch.com/feeds/topstories",
        "https://www.reuters.com/markets/feeds/rss",
        "https://www.wsj.com/xml/rss/3_7011.xml",
        "https://www.fxstreet.com/rss",
        "https://www.forexlive.com/feed/",
        "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
    ],
    "EU": [
        "https://www.ft.com/?format=rss",
        "https://www.reuters.com/markets/europe/rss",
        "https://www.fxstreet.com/rss",
        "https://www.forexlive.com/feed/",
        "https://cointelegraph.com/rss",
    ],
    "ASIA": [
        "https://asia.nikkei.com/rss/feed/nar",
        "https://www.reuters.com/finance/markets/asia/rss",
        "https://www.fxstreet.com/rss",
        "https://cointelegraph.com/rss",
    ],
    "AF": [
        "https://www.reuters.com/world/africa/rss",
        "https://www.fxstreet.com/rss",
        "https://cointelegraph.com/rss",
    ],
}

def regional_feeds(country: str) -> List[str]:
    country = (country or "US").upper()
    if country in ("US", "CA", "MX"): return REGIONAL_FEEDS["US"]
    if country in ("GB","DE","FR","NL","SE","ES","IT","IE","PL","PT","DK","FI","NO","BE"): return REGIONAL_FEEDS["EU"]
    if country in ("JP","KR","SG","HK","ID","MY","TH","PH","VN","IN","CN"): return REGIONAL_FEEDS["ASIA"]
    if country in ("NG","ZA","KE","EG","MA","GH","ET","TZ","UG","DZ"): return REGIONAL_FEEDS["AF"]
    return REGIONAL_FEEDS["DEFAULT"]

# --- exchange preferences by region (very rough defaults) ---
PREFS = {
    "US": ["binanceus", "coinbase", "kraken"],
    "EU": ["kraken", "bybit"],
    "ASIA": ["bybit", "okx", "kraken"],
    "AF": ["bybit", "kraken"],
    "DEFAULT": ["bybit", "kraken"],
}

def preferred_exchanges(country: str) -> List[str]:
    c = (country or "US").upper()
    if c in ("US", "CA", "MX"): return PREFS["US"]
    if c in ("GB","DE","FR","NL","SE","ES","IT","IE","PL","PT","DK","FI","NO","BE"): return PREFS["EU"]
    if c in ("JP","KR","SG","HK","ID","MY","TH","PH","VN","IN","CN"): return PREFS["ASIA"]
    if c in ("NG","ZA","KE","EG","MA","GH","ET","TZ","UG","DZ"): return PREFS["AF"]
    return PREFS["DEFAULT"]
# --- simple hostname-based environment detection ---
def detect_environment() -> str:
    """
    Detect the environment based on hostname.
    """
    hostname = socket.gethostname().lower()
    if "dev" in hostname: return "development"
    if "staging" in hostname: return "staging"
    return "production"