from __future__ import annotations

import math
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from allocators.portfolio import choose_assets
from allocators.ensemble import blend_weights, regime_weight_lambda
from allocators.sizing import vol_scaled_weights, apply_exposure_caps
from risk.adaptive_budget import compute_risk_parity_weights
from features.pipeline import compute_mu_cov
from features.validation import validate_features, FeatureValidationError
from ops.quarantine import should_quarantine
try:
    from ops.slack_notify import warn as slack_warn
except Exception:
    def slack_warn(title: str, reasons=None):
        return False
from research.regime import select_quantum_mode
from risk.calendar_gates import risk_gate
from strategies.meta_selector import BanditSelector, StratPath, daily_reward
from risk.adaptive_budget import stress_indicator, adaptive_budget
try:
    from observability.metrics import set_stress_s, set_leverage_l
except Exception:
    def set_stress_s(val: float):
        return None
    def set_leverage_l(val: float):
        return None
try:
    from config import Q_ENABLE_QUANTUM, Q_USE_RUNTIME
except Exception:
    Q_ENABLE_QUANTUM, Q_USE_RUNTIME = False, True
import logging
try:
    from observability.metrics import record_pnl_quantum, record_pnl_classical
except Exception:
    def record_pnl_quantum(v: float):
        return None

    def record_pnl_classical(v: float):
        return None
from sizer import suggest_size

try:
    from traders_core.router import ExchangeRouter  # preferred router
except Exception:
    # fallback shim if router not available
    ExchangeRouter = None  # type: ignore


def _symbol_to_pair(sym: str) -> str:
    s = sym.strip().upper()
    if "/" in s:
        return s
    if s.endswith("USDT"):
        return f"{s[:-4]}/USDT"
    if s.endswith("USD"):
        return f"{s[:-3]}/USD"
    # default to USDT quote
    return f"{s}/USDT"


def _estimate_equity(router) -> float:
    try:
        acc = router.account()
        if isinstance(acc, dict):
            if "paper_cash" in acc:
                return float(acc.get("paper_cash") or 0.0)
            bal = acc.get("balance") or {}
            # attempt to read USDT free/total
            if isinstance(bal, dict):
                try:
                    if "total" in bal and isinstance(bal["total"], dict):
                        v = bal["total"].get("USDT") or bal["total"].get("USD") or 0.0
                        return float(v or 0.0)
                except Exception:
                    pass
                try:
                    if "free" in bal and isinstance(bal["free"], dict):
                        v = bal["free"].get("USDT") or bal["free"].get("USD") or 0.0
                        return float(v or 0.0)
                except Exception:
                    pass
    except Exception:
        pass
    return 1000.0


def _compute_returns(df: pd.DataFrame) -> pd.DataFrame:
    # If the inputs look like price levels, use pct_change; otherwise, assume already returns
    try:
        # heuristic: if any value > 2, probably prices
        if float(np.nanmax(np.abs(df.values))) > 2.0:
            ret = df.pct_change().replace([np.inf, -np.inf], np.nan).dropna(how="all")
        else:
            ret = df.copy()
    except Exception:
        ret = df.copy()
    return ret.dropna()


def daily_rebalance_job(market_df: pd.DataFrame, latest_regime: str | None = None, budget: int = 10) -> Dict[str, Any]:
    """Quantum-aware portfolio selection and order placement.

    market_df: DataFrame with columns as symbols and rows as time (prices or returns).
    Returns a summary dict with selection and attempted orders.
    """
    if market_df is None or market_df.empty:
        return {"ok": False, "error": "empty market_df"}

    symbols = [str(c) for c in market_df.columns]
    # Calendar gate: skip or throttle
    try:
        from datetime import datetime, timezone

        gate = risk_gate(datetime.now(timezone.utc), exchange=None)
        if gate.get("block"):
            return {"ok": False, "error": "blocked_by_calendar", "reasons": gate.get("reasons", [])}
    except Exception:
        gate = {"throttle": {}}
    # Feature validation
    pre_df = market_df[symbols]
    try:
        validation = validate_features(pre_df)
    except FeatureValidationError as e:
        validation = {"ok": False, "issues": [str(e)]}
    quarantine, q_reasons = should_quarantine(validation)

    mu, Sigma = compute_mu_cov(pre_df)
    if mu.size == 0 or Sigma.size == 0:
        return {"ok": False, "error": "no returns/cov computed"}

    # regime-aware quantum gate
    q_on = select_quantum_mode(latest_regime, default_on=Q_ENABLE_QUANTUM)
    if q_on:
        logging.info("[rebalance] quantum path enabled for regime=%s", latest_regime)
    else:
        logging.info("[rebalance] quantum path disabled for regime=%s", latest_regime)

    x = choose_assets(mu, Sigma, budget=budget, force_quantum=q_on, force_use_runtime=Q_USE_RUNTIME).astype(int)
    # Also compute a classical baseline selection for PnL comparison
    x_classical = choose_assets(mu, Sigma, budget=budget, force_quantum=False, force_use_runtime=False).astype(int)
    selected = [sym for sym, sel in zip(symbols, x) if int(sel) == 1]

    # bootstrap router (paper/live determined via env)
    router = ExchangeRouter() if ExchangeRouter else None
    equity = _estimate_equity(router) if router else 1000.0

    # last known prices and previous for naive daily PnL snapshot
    last_row = market_df.iloc[-1]
    prev_row = market_df.iloc[-2] if len(market_df) >= 2 else last_row

    orders: List[Dict[str, Any]] = []
    for sym in selected:
        try:
            entry = float(last_row.get(sym) or 0.0)
        except Exception:
            entry = 0.0
        if not math.isfinite(entry) or entry <= 0:
            entry = 1.0
        # simple SL 2% below entry for sizing
        sl = entry * 0.98
        signal = {"symbol": sym, "entry": entry, "sl": sl, "market": "crypto-spot", "tf": "1h"}
        sized = suggest_size(signal, equity_usd=float(equity))
        qty = float(sized.get("qty") or 0.0)
        if qty <= 0 or router is None:
            orders.append({"symbol": sym, "qty": qty, "status": "skipped"})
            continue
        # place spot market order
        pair = _symbol_to_pair(sym)
        try:
            res = router.place_spot_market(pair, "buy", qty=qty)
            orders.append({"symbol": sym, "qty": qty, "result": res})
        except Exception as _e:
            orders.append({"symbol": sym, "qty": qty, "error": str(_e)})

    # Quick PnL snapshot for quantum vs classical (weights via simple sizer-based notionals)
    def _weights_for(selection: list[str], price_row: pd.Series) -> np.ndarray:
        w = []
        total = 0.0
        for sym in symbols:
            if sym in selection:
                entry = float(price_row.get(sym) or 0.0) or 1.0
                sl = entry * 0.98
                sized = suggest_size({"symbol": sym, "entry": entry, "sl": sl, "market": "crypto-spot", "tf": "1d"}, equity_usd=1.0)
                notional = float(sized.get("notional_usd") or 0.0)
            else:
                notional = 0.0
            total += notional
            w.append(notional)
        arr = np.asarray(w, dtype=float)
        return arr / total if total > 0 else arr

    # selections lists
    selected_q = [sym for sym, sel in zip(symbols, x) if int(sel) == 1]
    selected_c = [sym for sym, sel in zip(symbols, x_classical) if int(sel) == 1]

    # Volatility-scaled weights based on Sigma, then apply sector caps (if available)
    try:
        x_mask_q = np.array([1 if sel == 1 else 0 for sel in x], dtype=int)
        x_mask_c = np.array([1 if sel == 1 else 0 for sel in x_classical], dtype=int)
    except Exception:
        x_mask_q = np.ones(len(symbols), dtype=int)
        x_mask_c = np.ones(len(symbols), dtype=int)

    w_q = vol_scaled_weights(mu, Sigma, x_mask_q, cap=0.20)
    w_c = vol_scaled_weights(mu, Sigma, x_mask_c, cap=0.20)
    # Blend with risk parity weights for stability
    try:
        rp_q = compute_risk_parity_weights(Sigma, x_mask_q)
        rp_c = compute_risk_parity_weights(Sigma, x_mask_c)
        w_q = (w_q * 0.5 + rp_q * 0.5)
        w_c = (w_c * 0.5 + rp_c * 0.5)
        # renormalize L1
        w_q = w_q / max(1e-12, float(np.sum(np.abs(w_q))))
        w_c = w_c / max(1e-12, float(np.sum(np.abs(w_c))))
    except Exception:
        pass

    # sector_map placeholder (if you have metadata, plug it here)
    sector_map = None
    w_q = apply_exposure_caps(w_q, sector_map=sector_map, sector_cap=0.35)
    w_c = apply_exposure_caps(w_c, sector_map=sector_map, sector_cap=0.35)
    lam = regime_weight_lambda(latest_regime)
    # Load optional evolved lambda bias from storage/strategies.json
    try:
        import json, os
        with open(os.path.join("storage", "strategies.json"), "r", encoding="utf-8") as f:
            best = json.load(f).get("best", {})
            lb = float(best.get("lambda_bias", 1.0))
            lam = min(1.0, max(0.0, lam * lb))
    except Exception:
        pass
    # apply lambda throttle if present
    try:
        lam_max = float(gate.get("throttle", {}).get("lambda_max", lam))
        lam = min(lam, lam_max)
    except Exception:
        pass
    w_blend = blend_weights(w_q, w_c, lam=lam, norm=True)
    # next-day returns
    try:
        r_next = (last_row.values.astype(float) / (prev_row.values.astype(float) + 1e-12)) - 1.0
    except Exception:
        r_next = np.zeros(len(symbols), dtype=float)
    pnl_q = float(np.dot(w_q, r_next))
    pnl_c = float(np.dot(w_c, r_next))
    pnl_blend = float(np.dot(w_blend, r_next))
    try:
        record_pnl_quantum(pnl_q)
        record_pnl_classical(pnl_c)
    except Exception:
        pass

    # Meta-selector: pick which path to execute
    selector = BanditSelector()
    choice = selector.choose()
    if quarantine:
        logging.warning("[rebalance] feature quarantine active: %s", ",".join(q_reasons))
        try:
            slack_warn("Feature quarantine", q_reasons)
        except Exception:
            pass
        w_final = w_c * 0.25
        choice = StratPath.CLASSICAL
    else:
        if choice == StratPath.QUANTUM:
            w_final = w_q
        elif choice == StratPath.CLASSICAL:
            w_final = w_c
        else:
            w_final = w_blend
        logging.info("[rebalance] meta-selected path=%s", choice.value)

    # Apply size cap if provided by gate
    try:
        size_cap = float(gate.get("throttle", {}).get("size_cap", 1.0))
        if size_cap < 1.0 and size_cap > 0:
            w_final = w_final * size_cap
    except Exception:
        pass

    # Adaptive budget based on simple stress proxy
    try:
        import os
        # vol proxy from Sigma
        vol_proxy = float(np.sqrt(np.mean(np.clip(np.diag(Sigma), 1e-12, None))))
        vix_proxy = float(os.getenv("VIX_PROXY", "20"))
        liq_proxy = 1.0  # placeholder
        s = stress_indicator(vol_proxy, vix_proxy, liq_proxy)
        set_stress_s(s)
        w_final, L = adaptive_budget(w_final, s)
        set_leverage_l(L)
    except Exception:
        pass

    # Use selected weights for order targeting: allocate equity across symbols accordingly
    orders = []
    for i, sym in enumerate(symbols):
        w = float(w_final[i]) if i < len(w_final) else 0.0
        if w <= 0:
            continue
        entry = float(last_row.get(sym) or 0.0) or 1.0
        sl = entry * 0.98
        sized = suggest_size({"symbol": sym, "entry": entry, "sl": sl, "market": "crypto-spot", "tf": "1d"}, equity_usd=float(equity * w))
        qty = float(sized.get("qty") or 0.0)
        if qty <= 0 or router is None:
            orders.append({"symbol": sym, "qty": qty, "status": "skipped_blend"})
            continue
        pair = _symbol_to_pair(sym)
        try:
            res = router.place_spot_market(pair, "buy", qty=qty)
            orders.append({"symbol": sym, "qty": qty, "result": res, "w": w})
        except Exception as _e:
            orders.append({"symbol": sym, "qty": qty, "error": str(_e), "w": w})

    # Bandit update with reward = pnl / sqrt(turnover), modulated by sentiment
    try:
        from storage import kv
        from signals.sentiment_fusion import FusionModel

        prev_key = f"weights_prev_{choice.value}"
        prev = np.array(kv.get(prev_key, [0.0] * len(symbols)), dtype=float)
        cur = np.array(w_final, dtype=float)
        turnover = float(np.sum(np.abs(cur - prev)))
        pnl_map = {
            StratPath.QUANTUM: pnl_q,
            StratPath.CLASSICAL: pnl_c,
            StratPath.ENSEMBLE: pnl_blend,
        }
        reward = daily_reward(pnl_map.get(choice, 0.0), turnover)
        # Compute simple portfolio sentiment average (if events fed elsewhere)
        try:
            fm = FusionModel()
            sent_vals = []
            for i, sym in enumerate(symbols):
                if i < len(w_final) and w_final[i] > 0:
                    feats = fm.features(None, sym)
                    sent_vals.append(float(feats.get("sentiment", 0.0)))
            if sent_vals:
                avg_sent = float(np.mean(sent_vals))
                reward *= (1.0 + 0.1 * avg_sent)
        except Exception:
            pass
        selector.update(choice, reward)
        kv.set(prev_key, cur.tolist())
    except Exception:
        pass

    selected_final = [symbols[i] for i in range(len(symbols)) if (i < len(w_final) and w_final[i] > 0)]
    return {
        "ok": True,
        "regime": latest_regime,
        "q_enabled": bool(q_on),
        "chosen": int(sum(1 for _ in selected_final)),
        "selected": selected_final,
        "orders": orders,
        "pnl_q": pnl_q,
        "pnl_c": pnl_c,
        "pnl_blend": pnl_blend,
        "lambda": lam,
        "path": choice.value,
    }


__all__ = ["daily_rebalance_job"]
