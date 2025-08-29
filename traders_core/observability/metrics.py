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
            "realized_pnl",
            "Realized PnL (quote currency units, summed)",
            ["venue", "symbol"],
        )
        self.research_runs_total = Counter(
            "research_runs_total", "Research loop runs", ["venue","symbol"]
        )
        self.regime_flag = Gauge(
            "regime_flag",
            "1=storm,0=calm",
            ["venue", "symbol"],
        )

METRICS = _M()

# NOTE: Do not call `.labels(...).set(...)` at import time because the values
# (for example `symbol` or `regime_now`) are not available during module
# import in many runtime contexts. Use this module's `METRICS` instance from
# runtime code and set labels where the variables are defined, e.g.:
#
#   METRICS.regime_flag.labels(venue="crypto", symbol=the_symbol).set(1 if regime_now=="storm" else 0)

