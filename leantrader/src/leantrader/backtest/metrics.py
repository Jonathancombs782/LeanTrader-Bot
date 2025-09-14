import numpy as np
import pandas as pd


def sharpe(equity: pd.Series, rf: float = 0.0, period: int = 252):
    rets = equity.pct_change().fillna(0)
    if rets.std() == 0:
        return 0.0
    return (rets.mean() - rf / period) / (rets.std() + 1e-9) * np.sqrt(period)


def max_drawdown(equity: pd.Series):
    cummax = equity.cummax()
    dd = (equity / cummax) - 1.0
    return dd.min()
