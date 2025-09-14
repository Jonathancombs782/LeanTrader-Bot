import os, json
from typing import Optional
try:
    import redis
except Exception:
    redis = None

class Bus:
    def __init__(self, channel: str = "signal.web3.trending", redis_url: Optional[str] = None):
        self.channel = channel
        self.redis_url = redis_url or os.getenv("REDIS_URL", "").strip()
        self._client = None
        if self.redis_url and redis is not None:
            try:
                self._client = redis.from_url(self.redis_url, decode_responses=True)
                self._client.ping()
                print(f"[Bus] Redis connected: {self.redis_url}")
            except Exception as e:
                print(f"[Bus] Redis connect failed: {e}; using stdout")
                self._client = None
        elif self.redis_url and redis is None:
            print("[Bus] redis not installed; using stdout")

    def publish(self, message: dict):
        payload = json.dumps(message, separators=(",", ":"), ensure_ascii=False)
        if self._client:
            self._client.publish(self.channel, payload)
        else:
            print(f"[PUB {self.channel}] {payload}")

