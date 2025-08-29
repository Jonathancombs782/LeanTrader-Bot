# news_service.py
from __future__ import annotations

import csv, html, re, time
from pathlib import Path
from typing import List, Dict, Any

import feedparser
import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

DATA_DIR   = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
RAW_PATH   = DATA_DIR / "news_raw.csv"
CLEAN_PATH = DATA_DIR / "news_clean.csv"

DEFAULT_RSS = [
    # Crypto
    "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
    "https://cointelegraph.com/rss",
    "https://www.theblock.co/rss",
    # FX / Macro
    "https://www.forexlive.com/feed/",
    "https://www.fxstreet.com/rss",
    "https://www.marketwatch.com/feeds/topstories",
    "https://www.reuters.com/markets/feeds/rss",
]

RE_WORD = re.compile(r"[A-Za-z0-9_./+-]+")

CRYPTO_TICKER_WORDS = {
    "BTC":  ["btc","bitcoin"],
    "ETH":  ["eth","ethereum"],
    "SOL":  ["sol","solana"],
    "DOGE": ["doge","dogecoin"],
    "PEPE": ["pepe"],
}
FX_WORDS = {
    "USD": ["usd","dollar","us dollar","u.s. dollar","fomc","powell","cpi","ppi","nonfarm","payrolls","fed"],
    "EUR": ["eur","euro","ecb","lagarde","german","ifo","zew"],
    "GBP": ["gbp","pound","boe","bank of england","uk","britain","cable"],
    "JPY": ["jpy","yen","boj","bank of japan","usd/yen","yen carry"],
    "AUD": ["aud","aussie","rba","australia"],
    "NZD": ["nzd","kiwi","rbnz","new zealand"],
    "CAD": ["cad","loonie","boc","bank of canada"],
    "CHF": ["chf","swiss","snb"],
}

SIA = SentimentIntensityAnalyzer()

def _ts() -> int:
    return int(time.time())

def _ensure_files():
    if not RAW_PATH.exists():
        with open(RAW_PATH, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["ts","source","title","summary","link"])
    if not CLEAN_PATH.exists():
        with open(CLEAN_PATH, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["ts","source","title","summary","link","score","sent","hits"])

def harvest_rss(sources: List[str] | None = None, limit_per_feed: int = 80) -> int:
    """Append new items to RAW_PATH (dedup by link)."""
    _ensure_files()
    sources = sources or DEFAULT_RSS
    seen = set()
    try:
        df = pd.read_csv(RAW_PATH)
        seen = set(df["link"].astype(str).tolist())
    except Exception:
        pass

    added = 0
    with open(RAW_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for url in sources:
            try:
                feed = feedparser.parse(url)
                for e in (feed.entries or [])[:limit_per_feed]:
                    link = str(getattr(e, "link", "") or "")
                    if not link or link in seen:
                        continue
                    title   = html.unescape((getattr(e, "title", "") or "").strip())
                    summary = html.unescape((getattr(e, "summary", "") or getattr(e, "description", "") or "").strip())
                    w.writerow([_ts(), url, title, summary, link])
                    added += 1; seen.add(link)
            except Exception:
                continue
    return added

def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in RE_WORD.findall(text.lower())]

def _kw_for(symbol: str, is_fx: bool) -> List[str]:
    if is_fx:
        s = symbol.replace("/", "")
        tags = [s[:3].upper(), s[3:6].upper()]
        kws: List[str] = []
        for t in tags:
            kws += FX_WORDS.get(t, []) + [t.lower()]
        return list(dict.fromkeys(kws))
    base = symbol.split("/")[0].upper()
    return list(dict.fromkeys(CRYPTO_TICKER_WORDS.get(base, []) + [base.lower()]))

def _score_row(title: str, summary: str, kws: List[str]) -> tuple[float,float,list[str]]:
    text = f"{title} {summary}"
    toks = _tokenize(text)
    hits = {k for k in kws if k in toks}
    rel = len(hits)
    sent = float(SIA.polarity_scores(text).get("compound", 0.0))
    brev = max(0.8, min(1.2, 50.0 / max(10.0, len(title))))
    score = rel * brev * (1.0 + abs(sent))  # prefer strong sentiment + relevance
    return score, sent, sorted(hits)

def build_clean() -> int:
    """Recompute scores/sentiment and write CLEAN_PATH."""
    _ensure_files()
    try:
        raw = pd.read_csv(RAW_PATH)
    except Exception:
        return 0
    if raw.empty:
        return 0

    # pass-through now (we compute per-symbol on demand)
    raw["ts"]      = pd.to_numeric(raw["ts"], errors="coerce").fillna(_ts()).astype(int)
    raw["title"]   = raw["title"].fillna("")
    raw["summary"] = raw["summary"].fillna("")
    raw["source"]  = raw["source"].fillna("")
    raw["link"]    = raw["link"].fillna("")
    raw.to_csv(CLEAN_PATH, index=False)
    return len(raw)

def filtered_news_for(symbol: str, is_fx: bool, top_n: int = 5, min_score: float = 1.5) -> List[Dict[str,Any]]:
    _ensure_files()
    if not CLEAN_PATH.exists():
        return []
    try:
        df = pd.read_csv(CLEAN_PATH)
    except Exception:
        return []

    kws = _kw_for(symbol, is_fx)
    rows: List[Dict[str,Any]] = []
    for _, r in df.iterrows():
        sc, sent, hits = _score_row(str(r["title"]), str(r["summary"]), kws)
        if sc >= min_score:
            rows.append({
                "ts": int(r["ts"]),
                "source": str(r["source"]),
                "title": str(r["title"]),
                "summary": str(r["summary"]),
                "link": str(r["link"]),
                "score": float(sc),
                "sent": float(sent),
                "hits": hits
            })
    rows.sort(key=lambda x: x["score"], reverse=True)
    return rows[:top_n]

def bullets_for(symbol: str, is_fx: bool, top_n: int = 3) -> List[str]:
    out = []
    for r in filtered_news_for(symbol, is_fx, top_n=top_n):
        mood = "🟢" if r["sent"] > 0.25 else "🔴" if r["sent"] < -0.25 else "⚪"
        tag  = f" ({', '.join(r['hits'])})" if r["hits"] else ""
        src  = r.get("source","")
        out.append(f"{mood} {r['title']}{tag} — _{src}_")
    return out

if __name__ == "__main__":
    n = harvest_rss()
    m = build_clean()
    print(f"[news] harvested={n}, clean_rows={m}")
    for b in bullets_for("BTC/USD", is_fx=False):
        print(" -", b)
