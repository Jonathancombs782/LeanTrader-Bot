# regional_utils.py — region-aware feeds & exchange fallback
from __future__ import annotations
import os

def region() -> str:
    # allow override; default 'US'
    return (os.getenv("REGION") or os.getenv("GEO_COUNTRY") or "US").upper()

def regional_crypto_feeds() -> list[str]:
    r = region()
    if r in {"US", "CA"}:
        return [
            "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
            "https://cointelegraph.com/rss",
            "https://www.theblock.co/rss",
        ]
    # EU / ROW
    return [
        "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
        "https://www.fxstreet.com/cryptocurrencies/latest-news/rss",
        "https://cryptoslate.com/feed/",
    ]

def regional_fx_feeds() -> list[str]:
    r = region()
    base = [
        "https://www.reuters.com/markets/feeds/rss",
        "https://www.marketwatch.com/feeds/topstories",
        "https://www.fxstreet.com/rss",
        "https://www.forexlive.com/feed/",
    ]
    if r == "US":
        base.append("https://www.federalreserve.gov/feeds/press_all.xml")
    elif r in {"GB", "UK"}:
        base.append("https://www.bankofengland.co.uk/boeapps/rss/Pages/RSS.aspx?TaxonomyID=4")
    elif r == "EU":
        base.append("https://www.ecb.europa.eu/press/govcdec/html/index.en.html")
    return base

def primary_exchange() -> str:
    r = region()
    # prefer accessible venues per region; override with EXCHANGE_ID
    forced = os.getenv("EXCHANGE_ID")
    if forced:
        return forced
    if r in {"US"}:
        return "coinbase"   # ccxt id for Coinbase spot (widely accessible)
    # elsewhere bybit/binance may be ok
    return "bybit"

def fallback_exchange(curr: str) -> str:
    r = region()
    # rotate among a few that are typically available
    if r in {"US"}:
        return "kraken"
    return "okx"
# regional_utils.py