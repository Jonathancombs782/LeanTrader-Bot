from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from allocators.portfolio import choose_assets
from allocators.sizing import vol_scaled_weights, apply_exposure_caps
from allocators.ensemble import blend_weights
from features.pipeline import compute_mu_cov


@dataclass
class StrategyGenome:
    # indicator params / thresholds (example fields; extend as needed)
    lookback: int = 252
    min_history: int = 126
    budget: int = 10
    asset_cap: float = 0.20
    sector_cap: float = 0.35
    lambda_bias: float = 1.00  # multiplies ensemble lambda in pipeline (<=1 typical)
    # execution QUBO params (placeholders)
    exec_slices: int = 5
    exec_reps: int = 1


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def mutate(g: StrategyGenome, rng: np.random.Generator) -> StrategyGenome:
    g2 = StrategyGenome(**asdict(g))
    # mutate integers
    g2.lookback = int(_clamp(g2.lookback + rng.integers(-20, 21), 60, 500))
    g2.min_history = int(_clamp(g2.min_history + rng.integers(-10, 11), 30, g2.lookback))
    g2.budget = int(_clamp(g2.budget + rng.integers(-2, 3), 3, 25))
    # mutate floats
    g2.asset_cap = float(_clamp(g2.asset_cap + rng.normal(0, 0.03), 0.05, 0.50))
    g2.sector_cap = float(_clamp(g2.sector_cap + rng.normal(0, 0.05), 0.1, 0.7))
    g2.lambda_bias = float(_clamp(g2.lambda_bias + rng.normal(0, 0.05), 0.5, 1.2))
    g2.exec_slices = int(_clamp(g2.exec_slices + rng.integers(-1, 2), 2, 10))
    g2.exec_reps = int(_clamp(g2.exec_reps + rng.integers(-1, 2), 1, 3))
    return g2


def crossover(a: StrategyGenome, b: StrategyGenome, rng: np.random.Generator) -> StrategyGenome:
    fields = list(asdict(a).keys())
    child = {}
    for f in fields:
        child[f] = getattr(a if rng.random() < 0.5 else b, f)
    return StrategyGenome(**child)


def _pnl_series_from_weights(prices: pd.DataFrame, w: np.ndarray) -> np.ndarray:
    # daily returns
    r = prices.pct_change().fillna(0.0).to_numpy(dtype=float)
    # assume static weights for fast eval
    return (r @ w.astype(float)).reshape(-1)


def _max_drawdown(equity: np.ndarray) -> float:
    peak = -np.inf
    dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = max(dd, (peak - v) / peak if peak > 0 else 0.0)
    return float(dd)


def evaluate(g: StrategyGenome, prices_df: pd.DataFrame, seed: int = 123) -> Dict[str, float]:
    rng = np.random.default_rng(seed)
    # compute mu, Sigma
    mu, Sigma = compute_mu_cov(prices_df, window=int(g.lookback), min_history=int(g.min_history))
    if mu.size == 0 or Sigma.size == 0:
        return {"sharpe": 0.0, "pnl": 0.0, "max_dd": 0.0, "turnover": 0.0}
    # Classical and quantum paths; blend with tuned lambda bias
    x_c = choose_assets(mu, Sigma, budget=int(g.budget), force_quantum=False)
    w_c = vol_scaled_weights(mu, Sigma, x_c, cap=float(g.asset_cap))
    w_c = apply_exposure_caps(w_c, sector_map=None, sector_cap=float(g.sector_cap))
    try:
        x_q = choose_assets(mu, Sigma, budget=int(g.budget), force_quantum=True)
        w_q = vol_scaled_weights(mu, Sigma, x_q, cap=float(g.asset_cap))
        w_q = apply_exposure_caps(w_q, sector_map=None, sector_cap=float(g.sector_cap))
    except Exception:
        w_q = w_c
    lam = float(max(0.0, min(1.0, g.lambda_bias * 0.5)))  # base lam ~0.5 scaled by bias
    w = blend_weights(w_q, w_c, lam=lam, norm=True)
    pnl = _pnl_series_from_weights(prices_df, w)
    # Sharpe
    mu_p = float(np.mean(pnl)) if pnl.size else 0.0
    sd_p = float(np.std(pnl)) if pnl.size else 0.0
    sharpe = (mu_p / sd_p * math.sqrt(252.0)) if sd_p > 1e-12 else 0.0
    eq = (1.0 + pnl).cumprod()
    max_dd = _max_drawdown(eq)
    # Turnover (static weights -> zero);
    turnover = 0.0
    return {"sharpe": sharpe, "pnl": float(pnl.sum()), "max_dd": max_dd, "turnover": turnover}


def run_ga(
    prices_df: pd.DataFrame,
    pop: int = 30,
    gens: int = 20,
    elite: float = 0.1,
    mut_rate: float = 0.1,
    seed: int = 123,
) -> Tuple[StrategyGenome, List[Dict[str, float]]]:
    rng = np.random.default_rng(seed)
    # initialize population
    popu = [
        StrategyGenome(
            lookback=int(rng.integers(120, 300)),
            min_history=int(rng.integers(60, 150)),
            budget=int(rng.integers(5, 15)),
            asset_cap=float(rng.uniform(0.1, 0.3)),
            sector_cap=float(rng.uniform(0.2, 0.5)),
            lambda_bias=float(rng.uniform(0.7, 1.1)),
            exec_slices=int(rng.integers(3, 7)),
            exec_reps=1,
        )
        for _ in range(int(pop))
    ]
    leaderboard: List[Dict[str, float]] = []
    best: Tuple[float, StrategyGenome] = (-1e9, popu[0])

    for gen in range(int(gens)):
        scores = []
        for g in popu:
            res = evaluate(g, prices_df, seed)
            score = float(res.get("sharpe", 0.0))
            scores.append((score, g, res))
        scores.sort(key=lambda x: x[0], reverse=True)
        if scores[0][0] > best[0]:
            best = (scores[0][0], scores[0][1])
        leaderboard.append({"gen": gen, "best_sharpe": scores[0][0]})
        # selection: elites + offspring
        n_elite = max(1, int(elite * len(popu)))
        elites = [s[1] for s in scores[:n_elite]]
        new_pop = elites.copy()
        while len(new_pop) < len(popu):
            p1, p2 = rng.choice(elites), rng.choice([s[1] for s in scores[: len(popu) // 2]])
            child = crossover(p1, p2, rng)
            if rng.random() < mut_rate:
                child = mutate(child, rng)
            new_pop.append(child)
        popu = new_pop[: len(popu)]
    return best[1], leaderboard


__all__ = [
    "StrategyGenome",
    "mutate",
    "crossover",
    "evaluate",
    "run_ga",
]
