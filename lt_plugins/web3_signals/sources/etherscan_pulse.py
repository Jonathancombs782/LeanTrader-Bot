from typing import List, Dict, Any
import time
import requests
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

def fetch(api_key: str, contracts: List[str], blocks_lookback: int) -> List[Dict[str, Any]]:
    if not api_key or not contracts:
        return []
    base = "https://api.etherscan.io/api"
    try:
        latest = requests.get(base, params={"module":"proxy","action":"eth_blockNumber","apikey":api_key}, timeout=15).json()
        latest_block = int(latest.get("result","0x0"), 16)
    except Exception as e:
        print("[ETHERSCAN] latest block error:", e); return []
    start_block = max(0, latest_block - blocks_lookback)
    out = []
    for c in contracts:
        try:
            resp = requests.get(base, params={
                "module":"logs","action":"getLogs",
                "fromBlock":hex(start_block),"toBlock":hex(latest_block),
                "address":c,"topic0":TRANSFER_TOPIC,"apikey":api_key
            }, timeout=20).json()
            n = len(resp.get("result", []))
            if n > 0:
                out.append({
                    "source":"etherscan","chain":"ethereum","symbol":c[:6],
                    "pair":c,"score":min(100,n),"url":f"https://etherscan.io/token/{c}",
                    "transfer_count":n,"window_blocks":blocks_lookback,
                })
        except Exception as e:
            print("[ETHERSCAN] error:", c, e)
        time.sleep(0.2)
    return out

