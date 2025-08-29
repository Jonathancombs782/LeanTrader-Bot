# news_adapter.py
from __future__ import annotations

import os, time, json, re
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path

import requests  # pip install requests
try:
    import feedparser  # pip install feedparser
except Exception:
    feedparser = None  # optional

CACHE = Path("runtime"); CACHE.mkdir(parents=True, exist_ok=True)
CAL_PATH = CACHE / "calendar_cache.json"
CRYPTO_PATH = CACHE / "crypto_news_cache.json"

# -------- ForexFactory economic calendar (no key) --------
FF_THISWEEK = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FF_NEXTWEEK = "https://nfs.faireconomy.media/ff_calendar_nextweek.json"

def _load_json(p: Path) -> Any:
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

def _save_json(p: Path, data: Any) -> None:
    try:
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

def fetch_calendar(force: bool = False) -> List[Dict[str, Any]]:
    """Return list of events with keys: 'country','title','impact','timestamp'(ms),'forecast','actual'."""
    now = time.time()
    cache = _load_json(CAL_PATH) or {}
    if (not force) and cache.get("ts", 0) > now - 300:  # 5 min cache
        return cache.get("events", [])

    def _get(url: str) -> List[Dict[str, Any]]:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        out: List[Dict[str, Any]] = []
        for ev in data:
            try:
                out.append({
                    "country": ev.get("country", ""),
                    "title": ev.get("title", ""),
                    "impact": ev.get("impact", ""),  # "High", "Medium", ...
                    "timestamp": int(ev.get("timestamp") or ev.get("date") or 0),
                    "forecast": ev.get("forecast"),
                    "actual": ev.get("actual"),
                })
            except Exception:
                continue
        return out

    events = []
    try:
        events = _get(FF_THISWEEK)
        events += _get(FF_NEXTWEEK)
    except Exception:
        pass

    _save_json(CAL_PATH, {"ts": now, "events": events})
    return events

# Map symbol -> related currencies
def _fx_currencies_for_symbol(sym: str) -> Tuple[str, str]:
    sym = sym.upper()
    # EURUSD, GBPUSD, USDJPY...
    m = re.match(r"^([A-Z]{3})([A-Z]{3})$", sym.replace("/", ""))
    if not m: return ("","")
    return m.group(1), m.group(2)

def fx_guard_for_symbol(sym: str, hard_block_min: int = 10, soft_bias_min: int = 120) -> Dict[str, Any]:
    """
    Return guard/bias dict:
      { 'avoid_until': epoch_sec or 0,
        'bias': -1|0|+1, 'reason': '...' }
    - avoid trading N minutes around high-impact events of either currency.
    - If actual vs forecast is available AFTER release, infer a tiny bias.
    """
    now = int(time.time())
    A,B = _fx_currencies_for_symbol(sym)
    if not A or not B:
        return {"avoid_until": 0, "bias": 0, "reason": ""}

    events = fetch_calendar()
    avoid_until = 0
    bias = 0
    reasons: List[str] = []

    for ev in events:
        ccy = ev.get("country","").upper()
        if ccy not in (A, B, "USD","EUR","GBP","JPY","CHF","AUD","CAD","NZD","CNY"):
            continue
        ts_ms = int(ev.get("timestamp", 0))
        if ts_ms <= 0:
            continue
        ts = ts_ms // 1000
        # within hard-block window
        if abs(ts - now) <= hard_block_min * 60 and str(ev.get("impact","")).lower().startswith("high"):
            avoid_until = max(avoid_until, ts + hard_block_min * 60)
            reasons.append(f"HARD {ccy}:{ev.get('title','')}")
        # a soft bias if we have actual vs forecast and event is within last soft_bias_min
        if 0 <= (now - ts) <= soft_bias_min * 60:
            try:
                fc = float(str(ev.get("forecast")).split()[0])
                ac = float(str(ev.get("actual")).split()[0])
                if ac > fc: b = +1
                elif ac < fc: b = -1
                else: b = 0
                # If event currency is quote (e.g., USD in EURUSD), bias is inverted for the pair
                if ccy == B: b = -b
                bias += b
                reasons.append(f"BIAS {ccy}:{ev.get('title','')} {ac} vs {fc}")
            except Exception:
                continue

    # clamp bias to -1..+1
    if bias > 0: bias = 1
    if bias < 0: bias = -1
    return {"avoid_until": avoid_until, "bias": bias, "reason": "; ".join(reasons[:3])}

# -------- Crypto sentiment: CryptoPanic (optional key) + Coindesk/Cointelegraph RSS --------
def _sentiment_from_title(t: str) -> int:
    s = t.lower()
    good = ("approval","etf inflow","partnership","raised","surge","record","bull","upgrade","mainnet","win","victory","approved")
    bad  = ("hack","exploit","lawsuit","outflow","ban","halt","downgrade","bear","delist","fine","charge","indict")
    score = 0
    for k in good:
        if k in s: score += 1
    for k in bad:
        if k in s: score -= 1
    if "bitcoin" in s or "btc" in s: score += 0  # keep mapping by name
    return 1 if score > 0 else (-1 if score < 0 else 0)

def _symbols_from_title(t: str) -> List[str]:
    s = t.upper()
    out = []
    if "BTC" in s or "BITCOIN" in s: out.append("BTC/USDT")
    if "ETH" in s or "ETHEREUM" in s: out.append("ETH/USDT")
    if "XRP" in s: out.append("XRP/USDT")
    if "SOL" in s or "SOLANA" in s: out.append("SOL/USDT")
    if "DOGE" in s or "DOGECOIN" in s: out.append("DOGE/USDT")
    return out

def fetch_crypto_sentiment(force: bool = False) -> Dict[str, int]:
    """
    Return dict of symbol -> bias {-1,0,1} from recent headlines.
    Uses CryptoPanic if CRYPTOPANIC_TOKEN is set, else RSS from Coindesk/Cointelegraph.
    Cached for 2 minutes.
    """
    now = time.time()
    cache = _load_json(CRYPTO_PATH) or {}
    if (not force) and cache.get("ts", 0) > now - 120:
        return cache.get("bias", {})

    bias: Dict[str, int] = {}
    token = os.getenv("CRYPTOPANIC_TOKEN", "").strip()

    try:
        if token:
            url = f"https://cryptopanic.com/api/v1/posts/?auth_token={token}&regions=en&filter=rising&public=true"
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            data = r.json()
            for it in data.get("results", []):
                title = it.get("title", "")
                if not title: continue
                b = _sentiment_from_title(title)
                for sym in _symbols_from_title(title):
                    bias[sym] = max(min(bias.get(sym, 0) + b, 1), -1)
        else:
            # RSS (no key)
            if feedparser is not None:
                for rss in ("https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
                            "https://cointelegraph.com/rss"):
                    fp = feedparser.parse(rss)
                    for e in fp.get("entries", [])[:30]:
                        title = e.get("title", "")
                        b = _sentiment_from_title(title)
                        for sym in _symbols_from_title(title):
                            bias[sym] = max(min(bias.get(sym, 0) + b, 1), -1)
    except Exception:
        pass

    _save_json(CRYPTO_PATH, {"ts": now, "bias": bias})
    return bias
