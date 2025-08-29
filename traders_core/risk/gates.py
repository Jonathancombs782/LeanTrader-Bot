from __future__ import annotations
import numpy as np
import pandas as pd

def compute_metrics(returns: pd.Series) -> dict:
    ret = returns.fillna(0.0)
    mu = ret.mean()
    sd = ret.std() + 1e-12
    sharpe = (mu / sd) * (252**0.5)  # pseudo-annualized on bar basis
    hit = (ret > 0).mean()
    eq = (1 + ret).cumprod()
    peak = eq.cummax()
    dd = (eq / peak - 1.0).min()
    return {"oos_sharpe": float(sharpe), "hit_rate": float(hit), "max_dd": float(dd)}

def breach_daily_loss(equity_curve_today: pd.Series, max_daily_loss_pct: float) -> bool:
    if equity_curve_today.empty: return False
    peak = equity_curve_today.iloc[0]
    min_eq = equity_curve_today.min()
    drop = (min_eq - peak)/peak
    return drop <= -abs(max_daily_loss_pct)
