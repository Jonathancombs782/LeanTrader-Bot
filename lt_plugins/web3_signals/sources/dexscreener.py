from decimal import Decimal
from typing import List, Dict, Any
import time
import requests

def fetch(chains: list[str], min_liq: Decimal, min_vol5m: Decimal, min_chg5m: Decimal) -> List[Dict[str, Any]]:
    signals = []
    for chain in chains:
        url = f"https://api.dexscreener.com/latest/dex/pairs/{chain}"
        try:
            r = requests.get(url, timeout=15)
            pairs = r.json().get("pairs", [])[:200]
            for p in pairs:
                liq = Decimal(str(p.get("liquidity", {}).get("usd", 0)))
                vol24 = Decimal(str(p.get("volume", {}).get("h24", 0)))
                vol5m = vol24 / Decimal(24*12) if vol24 else Decimal("0")
                chg5m = Decimal(str(p.get("priceChange", {}).get("m5", 0)))
                if liq >= min_liq and vol5m >= min_vol5m and chg5m >= min_chg5m:
                    symbol = p.get("baseToken", {}).get("symbol") or (p.get("baseToken", {}).get("address","")[:6])
                    urlp = p.get("url") or f"https://dexscreener.com/{chain}"
                    score = int(min(100, (float(chg5m)*2) + min(50, float(liq)/10000)))
                    signals.append({
                        "source": "dexscreener",
                        "chain": chain,
                        "symbol": symbol,
                        "pair": p.get("pairAddress", ""),
                        "score": score,
                        "url": urlp,
                        "liquidity_usd": float(liq),
                        "change5m_pct": float(chg5m),
                    })
        except Exception as e:
            print(f"[DEX] {chain} error:", e)
        time.sleep(0.3)
    return signals

