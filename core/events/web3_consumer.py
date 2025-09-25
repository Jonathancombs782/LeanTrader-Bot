import os
import json
import sys
from typing import Callable, Optional
try:
    import redis
except Exception:
    redis = None

def subscribe(callback: Callable[[dict], None], channel: str = "signal.web3.trending", redis_url: Optional[str] = None):
    redis_url = redis_url or os.getenv("REDIS_URL", "").strip()
    if redis_url and redis is not None:
        r = redis.from_url(redis_url, decode_responses=True)
        pubsub = r.pubsub()
        pubsub.subscribe(channel)
        print(f"[web3_consumer] Subscribed to {channel} on {redis_url}")
        for msg in pubsub.listen():
            if msg.get("type") != "message": continue
            try:
                payload = json.loads(msg["data"])
                callback(payload)
            except Exception as e:
                print("[web3_consumer] parse error:", e, msg.get("data"))
    else:
        print("[web3_consumer] No REDIS_URL or redis not installed; reading JSON lines from stdin (dev mode)")
        for line in sys.stdin:
            line=line.strip()
            if not line: continue
            try:
                callback(json.loads(line))
            except Exception as e:
                print("[web3_consumer] stdin parse error:", e, line)

