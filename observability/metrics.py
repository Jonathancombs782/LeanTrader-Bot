from __future__ import annotations

import time
from contextlib import contextmanager

try:
    from prometheus_client import Counter, Histogram, Gauge  # type: ignore
except Exception:  # pragma: no cover
    Counter = None  # type: ignore
    Histogram = None  # type: ignore
    Gauge = None  # type: ignore


# Prometheus metrics (safe if prometheus_client unavailable)
if Counter is not None and Histogram is not None:
    METRIC_Q_SELECTIONS = Counter(
        "METRIC_Q_SELECTIONS",
        "Quantum allocator selections made",
    )
    METRIC_Q_FALLBACKS = Counter(
        "METRIC_Q_FALLBACKS",
        "Quantum allocator fallbacks to classical",
    )
    HIST_Q_SOLVE_MS = Histogram(
        "HIST_Q_SOLVE_MS",
        "QAOA solve duration (ms)",
        buckets=(5, 10, 25, 50, 100, 200, 400, 800, 1600, 3200, 6400),
    )
    CANARY_UP = Gauge(
        "leantrader_canary_up",
        "Process startup canary (1 when up)",
    )
    # Additional gauges/metrics
    OBJ_Q_VALUE = Gauge(
        "OBJ_Q_VALUE",
        "Last objective value from quantum selection (if available)",
    )
    ENSEMBLE_LAMBDA_G = Gauge(
        "ENSEMBLE_LAMBDA",
        "Last lambda used for ensemble blending",
    )
    EXEC_PLAN_MS = Histogram(
        "EXEC_PLAN_MS",
        "Execution plan duration (ms)",
        buckets=(5, 10, 25, 50, 100, 200, 400, 800, 1600, 3200, 6400),
    )
    # PnL metrics
    PNL_Q_SUM = Counter(
        "PNL_Q_SUM",
        "Cumulative PnL from quantum allocations",
        unit="currency",
    )
    PNL_C_SUM = Counter(
        "PNL_C_SUM",
        "Cumulative PnL from classical allocations",
        unit="currency",
    )
    PNL_Q_LAST = Gauge(
        "PNL_Q_LAST",
        "Last daily PnL quantum",
    )
    PNL_C_LAST = Gauge(
        "PNL_C_LAST",
        "Last daily PnL classical",
    )
    # Order quality metrics
    SLIPPAGE_BPS = Histogram(
        "SLIPPAGE_BPS",
        "Realized slippage in basis points",
        buckets=(1, 2, 5, 10, 20, 40, 80, 160, 320, 640),
    )
    ORDER_REJECTS = Counter(
        "ORDER_REJECTS",
        "Order rejects count",
    )
    ORDER_SENT = Counter(
        "ORDER_SENT",
        "Orders sent",
    )
    REJECT_RATE = Gauge(
        "REJECT_RATE",
        "rejects / sent (rolling calc outside or set periodically)",
    )
    MEMPOOL_RISK = Gauge(
        "MEMPOOL_RISK",
        "Estimated mempool sandwich/backrun risk [0,1]",
    )
    FLASH_HEDGE_COUNT = Counter(
        "FLASH_HEDGE_COUNT",
        "Emergency hedges due to flash crash detection",
    )
    LIQUIDITY_BLOCKS = Counter(
        "LIQUIDITY_BLOCKS",
        "Orders blocked or reduced by liquidity guard",
    )
else:  # pragma: no cover
    METRIC_Q_SELECTIONS = None
    METRIC_Q_FALLBACKS = None
    HIST_Q_SOLVE_MS = None
    CANARY_UP = None
    PNL_Q_SUM = None
    PNL_C_SUM = None
    PNL_Q_LAST = None
    PNL_C_LAST = None
    OBJ_Q_VALUE = None
    ENSEMBLE_LAMBDA_G = None
    EXEC_PLAN_MS = None
    SLIPPAGE_BPS = None
    ORDER_REJECTS = None
    ORDER_SENT = None
    REJECT_RATE = None
    MEMPOOL_RISK = None
    FLASH_HEDGE_COUNT = None
    LIQUIDITY_BLOCKS = None


def record_q_selection() -> None:
    try:
        if METRIC_Q_SELECTIONS is not None:
            METRIC_Q_SELECTIONS.inc()
    except Exception:
        pass


def record_q_fallback() -> None:
    try:
        if METRIC_Q_FALLBACKS is not None:
            METRIC_Q_FALLBACKS.inc()
    except Exception:
        pass


@contextmanager
def time_block(name: str):
    t0 = time.time()
    try:
        yield
    finally:
        try:
            dt_ms = (time.time() - t0) * 1000.0
            if HIST_Q_SOLVE_MS is not None:
                HIST_Q_SOLVE_MS.observe(float(dt_ms))
        except Exception:
            pass


def set_canary_up() -> None:
    try:
        if CANARY_UP is not None:
            CANARY_UP.set(1.0)
    except Exception:
        pass


def set_obj_q_value(val: float) -> None:
    try:
        if OBJ_Q_VALUE is not None:
            OBJ_Q_VALUE.set(float(val))
    except Exception:
        pass


def record_ensemble_lambda(val: float) -> None:
    try:
        if ENSEMBLE_LAMBDA_G is not None:
            ENSEMBLE_LAMBDA_G.set(float(val))
    except Exception:
        pass


def record_pnl_quantum(value: float) -> None:
    """Record quantum daily PnL (updates last and cumulative)."""
    try:
        v = float(value)
        if PNL_Q_LAST is not None:
            PNL_Q_LAST.set(v)
        if PNL_Q_SUM is not None:
            PNL_Q_SUM.inc(v)
    except Exception:
        pass


def record_pnl_classical(value: float) -> None:
    """Record classical daily PnL (updates last and cumulative)."""
    try:
        v = float(value)
        if PNL_C_LAST is not None:
            PNL_C_LAST.set(v)
        if PNL_C_SUM is not None:
            PNL_C_SUM.inc(v)
    except Exception:
        pass


# ---- Order quality helpers (with local ratio cache) ----
_sent_local = 0
_rej_local = 0


def record_slippage(bps: float) -> None:
    try:
        if SLIPPAGE_BPS is not None:
            SLIPPAGE_BPS.observe(float(bps))
    except Exception:
        pass


def record_order_sent(n: int = 1) -> None:
    global _sent_local
    try:
        _sent_local += int(n)
        if ORDER_SENT is not None:
            ORDER_SENT.inc(int(n))
        if REJECT_RATE is not None and _sent_local > 0:
            REJECT_RATE.set(float(_rej_local) / float(max(1, _sent_local)))
    except Exception:
        pass


def record_order_reject(n: int = 1) -> None:
    global _rej_local
    try:
        _rej_local += int(n)
        if ORDER_REJECTS is not None:
            ORDER_REJECTS.inc(int(n))
        if REJECT_RATE is not None and _sent_local > 0:
            REJECT_RATE.set(float(_rej_local) / float(max(1, _sent_local)))
    except Exception:
        pass


def set_reject_rate(rate: float) -> None:
    try:
        if REJECT_RATE is not None:
            REJECT_RATE.set(float(rate))
    except Exception:
        pass


def set_mempool_risk(val: float) -> None:
    try:
        if MEMPOOL_RISK is not None:
            MEMPOOL_RISK.set(float(max(0.0, min(1.0, val))))
    except Exception:
        pass


__all__ = [
    "METRIC_Q_SELECTIONS",
    "METRIC_Q_FALLBACKS",
    "HIST_Q_SOLVE_MS",
    "record_q_selection",
    "record_q_fallback",
    "time_block",
    "set_canary_up",
    "PNL_Q_SUM",
    "PNL_C_SUM",
    "PNL_Q_LAST",
    "PNL_C_LAST",
    "record_pnl_quantum",
    "record_pnl_classical",
    "OBJ_Q_VALUE",
    "ENSEMBLE_LAMBDA_G",
    "EXEC_PLAN_MS",
    "set_obj_q_value",
    "record_ensemble_lambda",
    "SLIPPAGE_BPS",
    "ORDER_REJECTS",
    "ORDER_SENT",
    "REJECT_RATE",
    "MEMPOOL_RISK",
    "set_mempool_risk",
    "LIQUIDITY_BLOCKS",
    "record_slippage",
    "record_order_sent",
    "record_order_reject",
    "set_reject_rate",
    "Counter",
    "Histogram",
    "FLASH_HEDGE_COUNT",
]
