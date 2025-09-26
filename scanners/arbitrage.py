from __future__ import annotations

from typing import Dict, List, Tuple, Any


def get_ticker(exchange: str, symbol: str) -> Dict[str, float]:
    """Fetch best bid/ask (fallback to last if needed). Uses ccxt via connector when available."""
    try:
        from traders_core.connectors.crypto_ccxt import _mk_exchange as mk_ex  # type: ignore

        ex = mk_ex(exchange, False)
        t = ex.safe_fetch_ticker(symbol) if hasattr(ex, "safe_fetch_ticker") else ex.fetch_ticker(symbol)
        return {
            "bid": float(t.get("bid") or t.get("close") or 0.0),
            "ask": float(t.get("ask") or t.get("close") or 0.0),
            "last": float(t.get("last") or t.get("close") or 0.0),
        }
    except Exception:
        return {"bid": 0.0, "ask": 0.0, "last": 0.0}


def get_orderbook(exchange: str, symbol: str) -> Dict[str, Any]:
    """Top-of-book snapshot for quick sizing (best bid/ask and sizes)."""
    try:
        from traders_core.connectors.crypto_ccxt import _mk_exchange as mk_ex  # type: ignore

        ex = mk_ex(exchange, False)
        ob = ex.fetch_order_book(symbol, limit=5)
        bids = ob.get("bids") or []
        asks = ob.get("asks") or []
        return {
            "bid": float(bids[0][0]) if bids else 0.0,
            "bid_size": float(bids[0][1]) if bids else 0.0,
            "ask": float(asks[0][0]) if asks else 0.0,
            "ask_size": float(asks[0][1]) if asks else 0.0,
        }
    except Exception:
        return {"bid": 0.0, "bid_size": 0.0, "ask": 0.0, "ask_size": 0.0}


def cross_exchange_spreads(symbols: List[str], venues: List[str], min_bps: float = 10.0) -> List[Dict[str, Any]]:
    """Find cross-exchange arbitrage spreads (sell venue highest bid, buy venue lowest ask)."""
    out: List[Dict[str, Any]] = []
    for sym in symbols:
        book: Dict[str, Dict[str, float]] = {}
        for v in venues:
            t = get_ticker(v, sym)
            if t.get("bid", 0) and t.get("ask", 0):
                book[v] = t
        if len(book) < 2:
            continue
        # choose min ask and max bid
        buy_v, buy = min(book.items(), key=lambda kv: kv[1]["ask"])
        sell_v, sell = max(book.items(), key=lambda kv: kv[1]["bid"])
        if sell_v == buy_v:
            continue
        spread = float(sell["bid"] - buy["ask"]) / max(1e-9, float(buy["ask"])) * 1e4
        if spread >= float(min_bps):
            oba = get_orderbook(buy_v, sym)
            obs = get_orderbook(sell_v, sym)
            size_cap = min(float(oba.get("ask_size", 0.0)), float(obs.get("bid_size", 0.0)))
            out.append({
                "symbol": sym,
                "buy_venue": buy_v,
                "sell_venue": sell_v,
                "buy": float(buy["ask"]),
                "sell": float(sell["bid"]),
                "spread_bps": float(spread),
                "size_cap": float(size_cap),
            })
    return out


def triangular_arbitrage(venue: str, pairs: List[Tuple[str, str, str]]) -> List[Dict[str, Any]]:
    """Simple triangular arb scanner on one venue using mid prices.

    pairs: list of (A/B, B/C, C/A)
    """
    def mid(v, s):
        t = get_ticker(v, s)
        b, a = float(t.get("bid", 0.0)), float(t.get("ask", 0.0))
        return (b + a) / 2.0 if b and a else float(t.get("last", 0.0))

    out: List[Dict[str, Any]] = []
    for (ab, bc, ca) in pairs:
        m1, m2, m3 = mid(venue, ab), mid(venue, bc), mid(venue, ca)
        if not (m1 and m2 and m3):
            continue
        # cycle: A->B->C->A; theoretical edge
        edge = (1.0 / m1) * (1.0 / m2) * m3 - 1.0
        bps = edge * 1e4
        if bps > 5:  # 5 bps threshold
            out.append({"venue": venue, "cycle": (ab, bc, ca), "edge_bps": float(bps)})
    return out


def risk_checks(opp: Dict[str, Any], min_volume: float = 0.001) -> bool:
    try:
        return float(opp.get("size_cap", 0.0)) >= float(min_volume)
    except Exception:
        return False


def plan_and_route(opp: Dict[str, Any], qty: float) -> Dict[str, Any]:
    """Plan execution using quantum_exec_plan to split across venues if provided.

    For cross-exchange opp: split qty across [buy_venue, sell_venue] with equal costs.
    """
    try:
        from execution.quantum_exec import quantum_exec_plan
    except Exception:
        quantum_exec_plan = None  # type: ignore
    venues = [opp.get("buy_venue"), opp.get("sell_venue")]
    venues = [v for v in venues if v]
    if quantum_exec_plan and len(venues) >= 1:
        return quantum_exec_plan(target_qty=float(qty), venues=venues, costs=[1.0] * len(venues))
    else:
        # fallback simple equal split
        per = float(qty) / max(1, len(venues))
        return {"plan": [{"venue": v, "qty": per} for v in venues], "method": "twap_equal"}


# Metrics helpers
try:
    from observability.metrics import Counter, Histogram, time_block
except Exception:  # pragma: no cover
    Counter = Histogram = None
    def time_block(name: str):
        from contextlib import contextmanager
        @contextmanager
        def _cm():
            yield
        return _cm()

ARB_OPPS = Counter("ARB_OPPS", "Arbitrage opportunities detected") if Counter else None
ARB_FILL_MS = Histogram("ARB_FILL_MS", "Arb fill latency (ms)", buckets=(5,10,25,50,100,200,400,800,1600,3200)) if Histogram else None


def record_arb_opp(n: int = 1):
    try:
        if ARB_OPPS is not None:
            ARB_OPPS.inc(int(n))
    except Exception:
        pass


__all__ = [
    "get_ticker",
    "get_orderbook",
    "cross_exchange_spreads",
    "triangular_arbitrage",
    "risk_checks",
    "plan_and_route",
    "record_arb_opp",
]

