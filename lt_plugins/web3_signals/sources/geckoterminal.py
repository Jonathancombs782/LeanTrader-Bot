from typing import List, Dict, Any
import time, requests

def fetch(networks: list[str], min_score: int) -> List[Dict[str, Any]]:
    signals = []
    for network in networks:
        url = f"https://api.geckoterminal.com/api/v2/networks/{network}/trending_pools"
        try:
            r = requests.get(url, timeout=15, headers={"Accept":"application/json"})
            pools = r.json().get("data", [])
            for pool in pools:
                attr = pool.get("attributes", {})
                symbol = attr.get("base_token_symbol") or attr.get("name","")[:8]
                score  = int(attr.get("gt_score", 0) or 0)
                if score >= min_score:
                    urlp = f"https://www.geckoterminal.com/{network}/pools/{pool.get('id','')}"
                    signals.append({
                        "source": "geckoterminal",
                        "chain": network,
                        "symbol": symbol,
                        "pair": pool.get("id",""),
                        "score": score,
                        "url": urlp,
                    })
        except Exception as e:
            print(f"[GECKO] {network} error:", e)
        time.sleep(0.3)
    return signals

