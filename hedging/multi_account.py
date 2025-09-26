from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


try:
    from prometheus_client import Gauge, Counter  # type: ignore

    NET_EXPOSURE_USD = Gauge("net_exposure_usd", "Net exposure per asset (USD)", ["asset"])  # current snapshot
    HEDGE_NOTIONAL_USD = Gauge(
        "hedge_notional_usd",
        "Planned/last executed hedge notional (USD)",
        ["asset", "instrument"],
    )
    HEDGE_UPDATES = Counter("hedge_updates_total", "Hedge plans computed/executed", ["action", "status"])
except Exception:  # pragma: no cover
    class _Noop:
        def labels(self, *_: Any, **__: Any) -> "_Noop":
            return self

        def set(self, *_: Any, **__: Any) -> None:
            pass

        def inc(self, *_: Any, **__: Any) -> None:
            pass

    NET_EXPOSURE_USD = _Noop()  # type: ignore
    HEDGE_NOTIONAL_USD = _Noop()  # type: ignore
    HEDGE_UPDATES = _Noop()  # type: ignore


def account_state(venue: Any) -> Dict[str, Any]:
    """Return positions and balances for a venue/router.

    Tries best-effort for ExchangeRouter-like, ccxt, or PaperBroker.
    Output schema:
      { 'id': 'bybit'|'binance'|'paper'|..., 'balances': {asset: free_usd}, 'positions': [{'symbol', 'asset', 'qty', 'px'}] }
    """
    state: Dict[str, Any] = {"id": str(getattr(venue, "id", "unknown")), "balances": {}, "positions": []}

    # balances
    try:
        bal = None
        if hasattr(venue, "safe_fetch_balance"):
            bal = venue.safe_fetch_balance()
        elif hasattr(venue, "fetch_balance"):
            try:
                bal = venue.fetch_balance()
            except Exception:
                bal = None
        if isinstance(bal, dict):
            total = bal.get("total") or bal.get("free") or {}
            for k, v in (total.items() if isinstance(total, dict) else {}):
                try:
                    state["balances"][str(k).upper()] = float(v)
                except Exception:
                    continue
    except Exception:
        pass

    # positions (best-effort)
    # Try paper broker style first
    try:
        if hasattr(venue, "positions") and callable(getattr(venue, "positions")):
            pos_list = venue.positions(None)
            for p in pos_list or []:
                sym = str(p.get("symbol"))
                qty = float(p.get("qty") or 0.0)
                asset = sym.split(":")[-1].split("/")[0] if "/" in sym else sym
                state["positions"].append({"symbol": sym, "asset": asset.upper(), "qty": qty, "px": float(p.get("entry") or 0.0)})
    except Exception:
        pass

    # ccxt futures positions (best-effort)
    try:
        ex = getattr(venue, "ex", venue)
        fetch = None
        for name in ("safe_fetch_positions", "fetch_positions"):
            if hasattr(ex, name):
                fetch = getattr(ex, name)
                break
        if fetch:
            try:
                pos = fetch()
            except TypeError:
                pos = fetch(None)
            for p in pos or []:
                try:
                    sym = str(p.get("symbol"))
                    side = str(p.get("side", "")).lower()
                    contracts = float(p.get("contracts") or p.get("positionAmt") or 0.0)
                    contract_size = float(p.get("contractSize") or 1.0)
                    dirn = 1.0 if side == "long" or contracts > 0 else -1.0
                    qty = dirn * abs(contracts) * contract_size
                    asset = sym.split("/")[0] if "/" in sym else sym
                    px = float(p.get("entryPrice") or p.get("avgPrice") or 0.0)
                    state["positions"].append({"symbol": sym, "asset": asset.upper(), "qty": qty, "px": px})
                except Exception:
                    continue
    except Exception:
        pass

    return state


def _last_price(venue: Any, symbol: str) -> float:
    try:
        if hasattr(venue, "last_price"):
            return float(venue.last_price(symbol))
        if hasattr(venue, "safe_fetch_ticker"):
            t = venue.safe_fetch_ticker(symbol)
            return float(t.get("last") or t.get("close") or 0.0)
        if hasattr(venue, "fetch_ticker"):
            t = venue.fetch_ticker(symbol)
            return float(t.get("last") or t.get("close") or 0.0)
    except Exception:
        return 0.0
    return 0.0


def net_exposure(venues: Sequence[Any], price_router: Optional[Any] = None) -> Dict[str, float]:
    """Compute net USD exposure by asset across venues.

    Aggregates spot balances (converted by price) and positions (qty*price with symbol mapping).
    """
    agg: Dict[str, float] = {}
    for v in venues:
        st = account_state(v)
        # balances as spot exposure: convert base coins to USD via symbol BASE/USDT when available
        for asset, qty in (st.get("balances") or {}).items():
            try:
                if asset in ("USD", "USDT", "USDC"):
                    usd = float(qty)
                else:
                    # prefer price_router for prices
                    sym = f"{asset}/USDT"
                    px = _last_price(price_router or v, sym)
                    usd = float(qty) * float(px)
                agg[asset] = agg.get(asset, 0.0) + usd
            except Exception:
                continue
        # positions (assume linear quote in USDT or priceable by router)
        for p in st.get("positions") or []:
            asset = str(p.get("asset") or "").upper()
            qty = float(p.get("qty") or 0.0)
            sym = str(p.get("symbol") or f"{asset}/USDT")
            px = float(p.get("px") or 0.0)
            if px <= 0:
                px = _last_price(price_router or v, sym if "/" in sym else f"{asset}/USDT")
            usd = qty * max(px, 0.0)
            agg[asset] = agg.get(asset, 0.0) + usd

    # export metrics snapshot
    for a, val in agg.items():
        try:
            NET_EXPOSURE_USD.labels(asset=a).set(float(val))
        except Exception:
            pass
    return agg


@dataclass
class Instrument:
    asset: str
    symbol: str
    kind: str = "futures"  # 'futures' | 'option'
    vol: float = 0.02  # daily vol proxy (for risk parity)
    delta: float = 1.0  # option delta proxy; use 1.0 for futures
    vega: float = 0.0  # option vega proxy per USD notional


def hedge_plan(
    exposures_usd: Mapping[str, float],
    instruments: Mapping[str, Sequence[Instrument]],
    min_usd: float = 500.0,
) -> List[Dict[str, Any]]:
    """Compute a min-variance (risk parity) hedge allocation for each asset.

    Returns list of items: {asset, instrument, symbol, side, notional_usd, weight}
    """
    plan: List[Dict[str, Any]] = []
    for asset, exp in exposures_usd.items():
        exp = float(exp)
        if abs(exp) < float(min_usd):
            continue
        insts = instruments.get(asset.upper()) or []
        vols = [max(1e-6, float(i.vol or 0.02)) for i in insts]
        if not insts or not vols:
            continue
        inv_vars = [1.0 / (v * v) for v in vols]
        s = sum(inv_vars) or 1.0
        weights = [iv / s for iv in inv_vars]
        side = "sell" if exp > 0 else "buy"  # short to hedge long, long to hedge short
        for w, i in zip(weights, insts):
            eff_delta = float(i.delta if i.kind == "option" else 1.0)
            eff_delta = eff_delta if abs(eff_delta) > 1e-6 else 1.0
            notional = -exp * float(w) / eff_delta
            plan.append(
                {
                    "asset": asset.upper(),
                    "instrument": i.kind,
                    "symbol": i.symbol,
                    "side": side,
                    "notional_usd": float(notional),
                    "weight": float(w),
                }
            )
            try:
                HEDGE_NOTIONAL_USD.labels(asset=asset.upper(), instrument=i.symbol).set(float(notional))
            except Exception:
                pass
    try:
        HEDGE_UPDATES.labels(action="plan", status="ok").inc()
    except Exception:
        pass
    return plan


def execute_hedge(plan: Sequence[Mapping[str, Any]], router: Optional[Any] = None) -> List[Dict[str, Any]]:
    """Execute hedge plan using ExchangeRouter if provided; otherwise dry-run.

    For futures hedges, computes qty = |notional| / last_price and sends market order with reduce_only=False.
    Returns list of execution results.
    """
    results: List[Dict[str, Any]] = []
    if router is None:
        try:
            from traders_core.router import ExchangeRouter  # type: ignore

            router = ExchangeRouter()
        except Exception:
            router = None

    for it in plan:
        sym = str(it.get("symbol"))
        side = str(it.get("side", "sell"))
        notional = abs(float(it.get("notional_usd", 0.0) or 0.0))
        if notional <= 0:
            continue
        if router is None:
            results.append({"symbol": sym, "side": side, "qty": 0.0, "ok": False, "error": "no router"})
            continue
        # fetch price via router
        try:
            px = 0.0
            if hasattr(router, "last_price"):
                px = float(router.last_price(sym))
            qty = max(0.0, notional / max(1e-9, px))
            if hasattr(router, "place_futures_market"):
                res = router.place_futures_market(sym, side, qty)
                ok = bool((res or {}).get("ok", True))
                results.append({"symbol": sym, "side": side, "qty": qty, "ok": ok, "result": res})
                try:
                    HEDGE_UPDATES.labels(action="execute", status=("ok" if ok else "err")).inc()
                except Exception:
                    pass
            else:
                results.append({"symbol": sym, "side": side, "qty": qty, "ok": False, "error": "no futures method"})
        except Exception as e:  # pragma: no cover
            results.append({"symbol": sym, "side": side, "qty": 0.0, "ok": False, "error": str(e)})
            try:
                HEDGE_UPDATES.labels(action="execute", status="err").inc()
            except Exception:
                pass
    return results


def hedge_plan_greeks(
    exposures_usd: Mapping[str, float],
    instruments: Mapping[str, Sequence[Instrument]],
    min_usd: float = 500.0,
) -> List[Dict[str, Any]]:
    """Greeks-aware hedge: solve for notional vector that neutralizes delta and vega when possible.

    Falls back to hedge_plan if underdetermined.
    """
    try:
        import numpy as np  # type: ignore
    except Exception:  # pragma: no cover
        return hedge_plan(exposures_usd, instruments, min_usd=min_usd)

    plan: List[Dict[str, Any]] = []
    for asset, usd in exposures_usd.items():
        usd = float(usd)
        if abs(usd) < float(min_usd):
            continue
        insts = instruments.get(asset.upper()) or []
        if not insts:
            continue
        # Target greeks: treat USD exposure as delta exposure; vega exposure unknown -> 0
        target = np.array([-usd, 0.0], dtype=float)
        A = np.zeros((2, len(insts)), dtype=float)
        for j, i in enumerate(insts):
            A[0, j] = float(i.delta if i.kind == "option" else 1.0)
            A[1, j] = float(i.vega if i.kind == "option" else 0.0)
        # Solve least-squares A x = target
        try:
            x, *_ = np.linalg.lstsq(A, target, rcond=None)
            for val, i in zip(x, insts):
                notional = float(val)
                side = "sell" if notional < 0 else "buy"
                plan.append(
                    {
                        "asset": asset.upper(),
                        "instrument": i.kind,
                        "symbol": i.symbol,
                        "side": side,
                        "notional_usd": abs(notional),
                        "weight": 0.0,
                    }
                )
                try:
                    HEDGE_NOTIONAL_USD.labels(asset=asset.upper(), instrument=i.symbol).set(abs(notional))
                except Exception:
                    pass
        except Exception:
            # Fallback
            plan.extend(hedge_plan({asset: usd}, {asset: insts}, min_usd=min_usd))
    try:
        HEDGE_UPDATES.labels(action="plan_greeks", status="ok").inc()
    except Exception:
        pass
    return plan


__all__ = [
    "NET_EXPOSURE_USD",
    "HEDGE_NOTIONAL_USD",
    "HEDGE_UPDATES",
    "account_state",
    "net_exposure",
    "Instrument",
    "hedge_plan",
    "hedge_plan_greeks",
    "hedge_plan_qp",
    "execute_hedge",
]


def hedge_plan_qp(
    exposures_usd: Mapping[str, float],
    instruments: Mapping[str, Sequence[Instrument]],
    bounds: Optional[Mapping[str, Tuple[float, float]]] = None,
    min_usd: float = 500.0,
) -> List[Dict[str, Any]]:
    """Constrained QP hedging: minimize ||x||^2 subject to A x = target and bounds.

    - x: vector of instrument notionals (USD signed)
    - A: rows [delta, vega]
    - target: [-exposure_usd, 0]
    Bounds dict maps instrument.symbol -> (min,max) in USD. Defaults to unbounded.
    """
    try:
        import cvxpy as cp  # type: ignore
        import numpy as np  # type: ignore
    except Exception:  # pragma: no cover
        return hedge_plan_greeks(exposures_usd, instruments, min_usd=min_usd)

    plan: List[Dict[str, Any]] = []
    bounds = bounds or {}
    for asset, usd in exposures_usd.items():
        usd = float(usd)
        if abs(usd) < float(min_usd):
            continue
        insts = instruments.get(asset.upper()) or []
        if not insts:
            continue
        n = len(insts)
        A = np.zeros((2, n), dtype=float)
        for j, i in enumerate(insts):
            A[0, j] = float(i.delta if i.kind == "option" else 1.0)
            A[1, j] = float(i.vega if i.kind == "option" else 0.0)
        target = np.array([-usd, 0.0], dtype=float)
        x = cp.Variable(n)
        cons = [A @ x == target]
        for j, i in enumerate(insts):
            lo, hi = bounds.get(i.symbol, (-cp.inf, cp.inf))  # type: ignore
            # allow env overrides HEDGE_QP_MIN/HEDGE_QP_MAX for global bounds
            if lo == -cp.inf and hi == cp.inf:  # type: ignore
                pass
            else:
                cons.append(x[j] >= float(lo))
                cons.append(x[j] <= float(hi))
        obj = cp.Minimize(cp.sum_squares(x))
        prob = cp.Problem(obj, cons)
        try:
            prob.solve(warm_start=True, solver=cp.OSQP)
        except Exception:
            prob.solve(warm_start=True)
        if x.value is None:
            # fallback
            plan.extend(hedge_plan_greeks({asset: usd}, {asset: insts}, min_usd=min_usd))
            continue
        for val, i in zip(list(x.value), insts):
            notional = float(val)
            side = "sell" if notional < 0 else "buy"
            plan.append(
                {
                    "asset": asset.upper(),
                    "instrument": i.kind,
                    "symbol": i.symbol,
                    "side": side,
                    "notional_usd": abs(notional),
                    "weight": 0.0,
                }
            )
            try:
                HEDGE_NOTIONAL_USD.labels(asset=asset.upper(), instrument=i.symbol).set(abs(notional))
            except Exception:
                pass
    try:
        HEDGE_UPDATES.labels(action="plan_qp", status="ok").inc()
    except Exception:
        pass
    return plan
