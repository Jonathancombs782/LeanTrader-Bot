from __future__ import annotations
from prometheus_client import Counter, Gauge, Histogram

class _M:
    def __init__(self):
        self.orders_total = Counter(
            "orders_total", "Orders sent", ["venue","symbol","status"]
        )
        self.last_signal = Gauge(
            "last_signal", "Last signal (1=long,0=flat)", ["venue","symbol"]
        )
        self.latest_prob = Gauge(
            "latest_prob", "Latest model long probability", ["venue","symbol"]
        )
        self.realized_pnl = Counter(
            "realized_pnl", "Realized PnL (quote currency units, summed)", ["venue","symbol"]
        )
        self.research_runs_total = Counter(
            "research_runs_total", "Research loop runs", ["venue","symbol"]
        )
        self.regime_flag = Gauge(
    "regime_flag", "1=storm,0=calm", ["venue","symbol"]
        )

METRICS = _M()
# crypto
METRICS.regime_flag.labels(venue="crypto", symbol=symbol).set(1 if regime_now=="storm" else 0)
# mt5
METRICS.regime_flag.labels(venue="mt5", symbol=symbol).set(1 if regime_now=="storm" else 0)
