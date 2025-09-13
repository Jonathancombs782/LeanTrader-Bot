from __future__ import annotations

import math
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple
from collections import deque, defaultdict


# ---- Metrics (GAUGE: MEMPOOL_RISK) -----------------------------------------
try:
    from prometheus_client import Gauge, Counter  # type: ignore

    MEMPOOL_RISK = Gauge(
        "mempool_risk",
        "Normalized 0..1 mempool sandwich risk level",
        ["symbol", "timeframe"],
    )
    FLASH_HEDGE_COUNT = Counter(
        "flash_hedge_count",
        "Number of emergency futures hedges triggered",
        ["reason", "symbol"],
    )
except Exception:  # pragma: no cover
    class _Noop:
        def labels(self, *_: Any, **__: Any) -> "_Noop":
            return self

        def set(self, *_: Any, **__: Any) -> None:
            pass

        def inc(self, *_: Any, **__: Any) -> None:
            pass

    MEMPOOL_RISK = _Noop()  # type: ignore
    FLASH_HEDGE_COUNT = _Noop()  # type: ignore


# ---- Tuning per symbol/timeframe -------------------------------------------

_TUNING: Dict[Tuple[str, str], Dict[str, float]] = {
    ("*", "*"): {"drop_bps": 10.0, "window_ms": 6000.0},
    ("ETH/USDC", "M1"): {"drop_bps": 15.0, "window_ms": 5000.0},
    ("ETH/USDC", "M5"): {"drop_bps": 12.0, "window_ms": 6000.0},
}


def set_mempool_tuning(symbol: str, timeframe: str, drop_bps: float, window_ms: float) -> None:
    _TUNING[(symbol.upper(), timeframe.upper())] = {
        "drop_bps": float(drop_bps),
        "window_ms": float(window_ms),
    }


def get_mempool_tuning(symbol: str, timeframe: str) -> Dict[str, float]:
    key = (symbol.upper(), timeframe.upper())
    if key in _TUNING:
        return _TUNING[key]
    return _TUNING[("*", "*")]


def load_mempool_tuning_from_file(path: str) -> int:
    """Load per-symbol/timeframe mempool tuning from YAML/JSON file.

    Expected structure:
      ETH/USDC:
        M1: {drop_bps: 15, window_ms: 5000}
        M5: {drop_bps: 12, window_ms: 6000}
      BTC/USDT:
        '*': {drop_bps: 10, window_ms: 7000}
    Returns number of entries loaded.
    """
    import json as _json  # lazy

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        return 0

    data: Dict[str, Any] = {}
    try:
        # Try YAML if available; otherwise try JSON
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(raw) or {}
        except Exception:
            data = _json.loads(raw)
    except Exception:
        return 0

    count = 0
    try:
        for sym, tf_map in (data or {}).items():
            if not isinstance(tf_map, dict):
                continue
            for tf, vals in tf_map.items():
                try:
                    set_mempool_tuning(sym, tf, float(vals.get("drop_bps", 10.0)), float(vals.get("window_ms", 6000.0)))
                    count += 1
                except Exception:
                    continue
    except Exception:
        return count
    return count


# ---- Mempool sandwich risk monitor ----------------------------------------

@dataclass
class _Tx:
    ts: float
    tx_hash: str
    pair: str
    gas_price: float
    max_fee: float
    amount_in_usd: float
    from_addr: str = ""
    method: str = ""


def _extract_tx(tx: Mapping[str, Any]) -> Optional[_Tx]:
    try:
        ts = float(tx.get("ts", time.time()))
        tx_hash = str(tx.get("hash", ""))
        pair = str(tx.get("pair") or tx.get("symbol") or tx.get("pool") or "?")
        gp = tx.get("gas_price")
        max_fee = tx.get("maxFeePerGas", gp)
        gas_price = float(gp if gp is not None else 0)
        max_fee = float(max_fee if max_fee is not None else gas_price)
        amt_usd = tx.get("amount_usd") or tx.get("notional_usd") or tx.get("value_usd")
        if amt_usd is None and tx.get("amount") is not None and tx.get("price_usd") is not None:
            amt_usd = float(tx["amount"]) * float(tx["price_usd"])  # type: ignore[index]
        amount_in_usd = float(amt_usd) if amt_usd is not None else 0.0
        from_addr = str(tx.get("from", ""))
        method = str(tx.get("method", ""))
        if not tx_hash:
            tx_hash = f"{pair}:{ts}"
        return _Tx(ts=ts, tx_hash=tx_hash, pair=pair, gas_price=gas_price, max_fee=max_fee, amount_in_usd=amount_in_usd, from_addr=from_addr, method=method)
    except Exception as e:  # pragma: no cover
        logging.debug("_extract_tx failed: %s", e)
        return None


@dataclass
class MempoolMonitor:
    symbol: str
    timeframe: str
    window_ms: float
    drop_bps: float
    _buf: Deque[_Tx] = field(default_factory=deque)
    _by_pair: Dict[str, Deque[_Tx]] = field(default_factory=lambda: defaultdict(deque))
    current_risk: float = 0.0

    def observe(self, tx: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        """Observe a pending tx; update risk if suspicious patterns are found.

        Returns an event dict when a sandwich risk is detected, else None.
        """
        itx = _extract_tx(tx)
        if itx is None:
            return None

        now = itx.ts
        cutoff = now - (self.window_ms / 1000.0)

        # Evict old
        while self._buf and self._buf[0].ts < cutoff:
            old = self._buf.popleft()
            q = self._by_pair.get(old.pair)
            if q:
                while q and q[0].ts < cutoff:
                    q.popleft()

        # Add
        self._buf.append(itx)
        self._by_pair[itx.pair].append(itx)

        # Detect patterns: gas price staircasing and repeated pair touch
        ev = None
        pair_q = self._by_pair[itx.pair]

        if len(pair_q) >= 3:
            # Consider last 3 tx for staircase and backrun sandwich shape
            a, b, c = pair_q[-3], pair_q[-2], pair_q[-1]
            # Gas bump suspicion: monotonically increasing gas price with tight spacing
            gas_bump = (a.gas_price < b.gas_price < c.gas_price) or (a.max_fee < b.max_fee < c.max_fee)
            tight_timing = (c.ts - a.ts) <= (self.window_ms / 1000.0) * 0.5
            same_pair = a.pair == b.pair == c.pair
            different_senders = len({a.from_addr, b.from_addr, c.from_addr} - {""}) >= 2

            if same_pair and gas_bump and tight_timing and different_senders:
                # Compute magnitude via relative gas gap vs median in window
                gas_vals = [t.gas_price or t.max_fee for t in pair_q]
                base = max(1.0, sorted(gas_vals)[len(gas_vals) // 2])
                severity = min(1.0, (c.gas_price - a.gas_price) / base)
                # Risk accumulate with amount size factor
                notional = max(a.amount_in_usd, b.amount_in_usd, c.amount_in_usd)
                size_factor = min(1.0, notional / 250_000.0)

                # Increase risk; decay old risk slightly
                self.current_risk = max(0.0, self.current_risk * 0.85)
                incr = 0.35 + 0.5 * severity + 0.3 * size_factor
                self.current_risk = min(1.0, self.current_risk + incr)

                ev = {
                    "type": "mempool_sandwich_pattern",
                    "pair": itx.pair,
                    "gas_increase": c.gas_price - a.gas_price,
                    "severity": round(severity, 3),
                    "size_factor": round(size_factor, 3),
                    "risk": round(self.current_risk, 3),
                    "ts": now,
                }

        # Also raise slight risk when burst of same-pair touches within window
        touches = len(pair_q)
        if touches >= 6:
            self.current_risk = min(1.0, max(self.current_risk, 0.5))

        # Record gauge
        try:
            MEMPOOL_RISK.labels(symbol=self.symbol.upper(), timeframe=self.timeframe.upper()).set(float(self.current_risk))
        except Exception:  # pragma: no cover
            pass

        return ev


def mempool_monitor(
    subscription: Iterable[Mapping[str, Any]],
    symbol: str = "ETH/USDC",
    timeframe: str = "M1",
) -> Dict[str, Any]:
    """Consume a subscription of pending tx dicts and compute mempool risk.

    Returns a summary dict with latest risk and last event (if any).
    """
    tune = get_mempool_tuning(symbol, timeframe)
    mon = MempoolMonitor(symbol=symbol, timeframe=timeframe, window_ms=tune["window_ms"], drop_bps=tune["drop_bps"])

    last_event: Optional[Dict[str, Any]] = None
    for tx in subscription:
        ev = mon.observe(tx)
        if ev:
            last_event = ev

    return {"risk": mon.current_risk, "last_event": last_event}


# ---- Dynamic slippage ------------------------------------------------------

def dynamic_slippage(max_bps: float, risk: float) -> int:
    """Decrease slippage when mempool risk is high.

    Returns integer bps (basis points) to use.
    """
    max_bps = float(max_bps)
    r = max(0.0, min(1.0, float(risk)))
    # At r=0 -> 100% of max; r=1 -> 35% of max (keep some room)
    scale = 1.0 - 0.65 * r
    bps = int(max(1.0, math.floor(max_bps * scale)))
    return bps


# ---- Private transaction mode ---------------------------------------------

class PrivateTxClient:
    """Very small adapter for Flashbots/MEV-Share like clients.

    The instance should implement a send(raw_tx: bytes|str, **kwargs) -> Dict or raise.
    This class wraps a callable to keep dependencies optional.
    """

    def __init__(self, sender: Callable[..., Any]):
        self._sender = sender

    def available(self) -> bool:
        return callable(self._sender)

    def send(self, raw_tx: Any, **kwargs: Any) -> Any:
        return self._sender(raw_tx, **kwargs)


def private_tx_mode(
    notional_usd: float,
    risk: float,
    threshold_usd: float = 250_000.0,
) -> bool:
    """Decide whether to prefer private route (Flashbots/MEV-Share)."""

    big = float(notional_usd) >= float(threshold_usd)
    high_risk = float(risk) >= 0.6
    return bool(big or high_risk)


# ---- Emergency futures hedge ----------------------------------------------

def emergency_hedge(
    hedger: Any,
    symbol: str,
    side: str,
    notional_usd: float,
    leverage: float = 1.0,
    reason: str = "mempool_risk",
    extra: Optional[Dict[str, Any]] = None,
) -> Optional[Any]:
    """Trigger a hedge via a provided futures hedger integration.

    The `hedger` is expected to expose either
      - hedge(symbol, side, notional_usd, leverage, **extra)
      - or place_hedge / market_order equivalent methods.
    """
    if hedger is None:
        logging.warning("No hedger provided for emergency_hedge")
        return None

    side = side.lower()  # 'buy' to hedge short exposure; 'sell' to hedge long
    if extra is None:
        extra = {}

    try:
        if hasattr(hedger, "hedge") and callable(getattr(hedger, "hedge")):
            resp = hedger.hedge(symbol=symbol, side=side, notional_usd=float(notional_usd), leverage=float(leverage), **extra)
        elif hasattr(hedger, "market_order") and callable(getattr(hedger, "market_order")):
            qty = extra.get("qty")
            resp = hedger.market_order(symbol=symbol, side=side, qty=qty, notional=notional_usd, leverage=leverage, reduce_only=False)
        elif hasattr(hedger, "place_order") and callable(getattr(hedger, "place_order")):
            resp = hedger.place_order(symbol=symbol, side=side, type="market", notional=notional_usd, leverage=leverage, reduce_only=False)
        else:
            logging.warning("Hedger has no supported method; skipping emergency hedge")
            resp = None
    except Exception as e:  # pragma: no cover
        logging.exception("Emergency hedge failed: %s", e)
        resp = None

    if resp is not None:
        try:
            FLASH_HEDGE_COUNT.labels(reason=reason, symbol=symbol.upper()).inc()
        except Exception:
            pass

    return resp


__all__ = [
    "MEMPOOL_RISK",
    "FLASH_HEDGE_COUNT",
    "set_mempool_tuning",
    "get_mempool_tuning",
    "MempoolMonitor",
    "mempool_monitor",
    "dynamic_slippage",
    "PrivateTxClient",
    "private_tx_mode",
    "emergency_hedge",
    "load_mempool_tuning_from_file",
]
