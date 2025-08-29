# build_universe.py
from __future__ import annotations
import json, re, os
from pathlib import Path

def build(exchange_id: str, quotes=("USDT","USD"), min_cost_usd: float = 5.0):
    import ccxt
    ex = getattr(ccxt, exchange_id)({"enableRateLimit": True, "timeout": 15000})
    markets = ex.load_markets()
    syms = []
    bad = re.compile(r"(UP|DOWN|3L|3S|BULL|BEAR|PERP|^[A-Z]+_[A-Z]+)$", re.I)
    for m in markets.values():
        if m.get("active") is False: 
            continue
        if m.get("spot") is False:
            continue
        base, quote = m.get("base"), m.get("quote")
        symbol = m.get("symbol")
        if not base or not quote or not symbol:
            continue
        if quote.upper() not in quotes:
            continue
        if bad.search(symbol):
            continue
        # estimate min notional if available
        md = m.get("limits",{}).get("cost",{}).get("min")
        if md is not None and isinstance(md, (int,float)) and md > 0 and md > min_cost_usd:
            continue
        syms.append(symbol)
    syms = sorted(set(syms))
    outdir = Path("data"); outdir.mkdir(exist_ok=True, parents=True)
    outf = outdir / f"symbols_{exchange_id}.json"
    outf.write_text(json.dumps({"exchange": exchange_id, "symbols": syms}, indent=2))
    print(f"wrote {len(syms)} symbols -> {outf}")

if __name__ == "__main__":
    for ex in ("bybit","kraken","binanceus"):
        try:
            build(ex)
        except Exception as e:
            print(f"{ex}: {e}")
