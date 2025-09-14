from __future__ import annotations

import json
import math
import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from features.pipeline import compute_mu_cov
from allocators.portfolio import choose_assets
from sizer import suggest_size


def _next_day_returns(prices: pd.DataFrame, t: int) -> np.ndarray:
    # simple returns for day t+1 relative to t
    p0 = prices.iloc[t].to_numpy(dtype=float)
    p1 = prices.iloc[t + 1].to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = (p1 / np.maximum(p0, 1e-12)) - 1.0
    r[~np.isfinite(r)] = 0.0
    return r


def _weights_from_sizer(symbols: List[str], prices_row: pd.Series, selected_idx: np.ndarray, equity: float = 1.0) -> np.ndarray:
    # Use existing suggest_size to map to notionals then normalize to weights
    notionals = []
    for i, sym in enumerate(symbols):
        if i not in selected_idx:
            notionals.append(0.0)
            continue
        try:
            entry = float(prices_row.get(sym) or 0.0)
        except Exception:
            entry = 0.0
        if not math.isfinite(entry) or entry <= 0:
            entry = 1.0
        sl = entry * 0.98
        sized = suggest_size({"symbol": sym, "entry": entry, "sl": sl, "market": "crypto-spot", "tf": "1d"}, equity_usd=equity)
        notionals.append(float(sized.get("notional_usd") or 0.0))
    arr = np.asarray(notionals, dtype=float)
    tot = float(arr.sum())
    if tot <= 0:
        # equal weight among selected
        w = np.zeros_like(arr)
        if len(selected_idx) > 0:
            w[selected_idx] = 1.0 / float(len(selected_idx))
        return w
    return arr / tot


def _ensure_binary(x: np.ndarray, budget: int) -> np.ndarray:
    x = np.asarray(x).reshape(-1)
    idx = np.argsort(-x)[: int(budget)]
    out = np.zeros_like(x, dtype=int)
    out[idx] = 1
    return out


def _quantum_select_direct(mu: np.ndarray, Sigma: np.ndarray, budget: int, seed: int) -> Optional[np.ndarray]:
    qpo = None
    for _mod in ("quantum_portfolio", "quantum", "traders_core.quantum_portfolio"):
        try:
            m = __import__(_mod, fromlist=["quantum_portfolio_optimize"])  # type: ignore
            if hasattr(m, "quantum_portfolio_optimize"):
                qpo = getattr(m, "quantum_portfolio_optimize")
                break
        except Exception:
            continue
    if qpo is None:
        return None
    use_runtime = os.getenv("Q_USE_RUNTIME", "false").strip().lower() in ("1", "true", "yes", "on")
    try:
        y = qpo(returns=mu, covariance=Sigma, budget=int(budget), reps=2, resilience_level=1, use_runtime=use_runtime, seed=int(seed))
        return _ensure_binary(np.asarray(y), budget)
    except Exception:
        return None


def run_ab_backtest(prices_df: pd.DataFrame, budget: int = 10, window: int = 252, seed: int = 123) -> Dict[str, Dict[str, object]]:
    """Run A/B backtest comparing classical vs quantum allocator.

    Returns dict with keys: classical, quantum, meta. Each track contains
    pnl_series (list), total_pnl (float), sharpe (float), turns (int).
    """
    if prices_df is None or prices_df.empty:
        raise ValueError("prices_df is empty")

    rng = np.random.default_rng(int(seed))
    symbols = [str(c) for c in prices_df.columns]
    n_days = prices_df.shape[0]
    start = int(window)
    end = n_days - 1  # need t+1
    if start + 1 >= n_days:
        raise ValueError("not enough rows for given window")

    pnl_c: List[float] = []
    pnl_q: List[float] = []
    prev_sel_c = None
    prev_sel_q = None
    turns_c = 0
    turns_q = 0

    for t in range(start, end):
        look = prices_df.iloc[t - window : t]
        mu, Sigma = compute_mu_cov(look, window=window, min_history=min(window // 2, 126))
        if mu.size == 0 or Sigma.size == 0:
            pnl_c.append(0.0)
            pnl_q.append(0.0)
            continue

        # Classical selection (force_quantum=False)
        x_c = choose_assets(mu, Sigma, budget=budget, force_quantum=False).astype(int)
        sel_c_idx = np.where(x_c == 1)[0]
        if prev_sel_c is not None:
            # count asset changes
            turns_c += int(np.sum(np.abs(x_c - prev_sel_c)))
        prev_sel_c = x_c.copy()

        # Quantum selection: try direct call with seed, else fall back to choose_assets with force_quantum=True
        x_q = _quantum_select_direct(mu, Sigma, budget=budget, seed=seed)
        if x_q is None:
            x_q = choose_assets(mu, Sigma, budget=budget, force_quantum=True).astype(int)
        sel_q_idx = np.where(x_q == 1)[0]
        if prev_sel_q is not None:
            turns_q += int(np.sum(np.abs(x_q - prev_sel_q)))
        prev_sel_q = x_q.copy()

        # Weights via sizer (normalize notionals)
        w_c = _weights_from_sizer(symbols, prices_df.iloc[t], sel_c_idx, equity=1.0)
        w_q = _weights_from_sizer(symbols, prices_df.iloc[t], sel_q_idx, equity=1.0)

        # Next-day returns
        r_next = _next_day_returns(prices_df[symbols], t)
        pnl_c.append(float(np.dot(w_c, r_next)))
        pnl_q.append(float(np.dot(w_q, r_next)))

    def _kpis(pnl: List[float]) -> Tuple[float, float]:
        arr = np.asarray(pnl, dtype=float)
        mu = float(np.mean(arr)) if arr.size else 0.0
        sd = float(np.std(arr)) if arr.size else 0.0
        sharpe = (mu / sd * math.sqrt(252.0)) if sd > 1e-12 else 0.0
        return float(arr.sum()), sharpe

    total_c, sharpe_c = _kpis(pnl_c)
    total_q, sharpe_q = _kpis(pnl_q)

    return {
        "classical": {
            "pnl_series": [float(x) for x in pnl_c],
            "total_pnl": float(total_c),
            "sharpe": float(sharpe_c),
            "turns": int(turns_c),
        },
        "quantum": {
            "pnl_series": [float(x) for x in pnl_q],
            "total_pnl": float(total_q),
            "sharpe": float(sharpe_q),
            "turns": int(turns_q),
        },
        "meta": {
            "n_assets": int(len(symbols)),
            "n_days": int(n_days),
            "window": int(window),
            "budget": int(budget),
            "seed": int(seed),
        },
    }


def _main_cli():
    import argparse

    p = argparse.ArgumentParser(description="Quantum A/B backtest")
    p.add_argument("--csv", dest="csv", default=None)
    p.add_argument("--budget", type=int, default=10)
    p.add_argument("--window", type=int, default=252)
    p.add_argument("--seed", type=int, default=123)
    args = p.parse_args()

    try:
        if args.csv and os.path.exists(args.csv):
            df = pd.read_csv(args.csv)
            if "time" in df.columns:
                df = df.set_index("time")
        else:
            # synthetic data for convenience
            rng = np.random.default_rng(args.seed)
            cols = [f"A{i}" for i in range(8)]
            data = {}
            for i, c in enumerate(cols):
                steps = rng.normal(0.0005 - 0.0001 * (i % 3), 0.01, size=400)
                data[c] = 100 * np.cumprod(1.0 + steps)
            idx = pd.date_range(end=pd.Timestamp.utcnow().floor("min"), periods=400, freq="1min")
            df = pd.DataFrame(data, index=idx)
        res = run_ab_backtest(df, budget=args.budget, window=args.window, seed=args.seed)
        print(json.dumps(res))
        return 0
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(_main_cli())

