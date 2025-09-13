import os

import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


class GlobalRiskLock:
    def __init__(self, prefix="leantrader"):
        self.r = redis.Redis.from_url(REDIS_URL)
        self.prefix = prefix

    def key(self, k):
        return f"{self.prefix}:{k}"

    def set_drawdown_lock(self, hours=24):
        self.r.setex(self.key("dd_lock"), hours * 3600, "1")

    def is_locked(self) -> bool:
        return self.r.exists(self.key("dd_lock")) == 1

    def clear(self):
        self.r.delete(self.key("dd_lock"))
