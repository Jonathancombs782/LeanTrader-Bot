import pandas as pd

from ..execution.tcost import expected_cost
from ..risk.guardrails import position_size


def backtest(df: pd.DataFrame, signals: pd.DataFrame, risk_cfg, spread_pts: float = 0.0002):
    equity = 1.0
    bal_hist = []
    for ts, row in signals.iterrows():
        bal_hist.append(equity)
        if row.get("go", 0) <= 0 or row["side"] is None:
            continue
        side = row["side"]
        px = df.loc[ts, "close"]
        atr = (df["high"] - df["low"]).rolling(14).mean().loc[ts]
        sl = px - 1.5 * atr if side == "long" else px + 1.5 * atr
        tp = px + 2.0 * atr if side == "long" else px - 2.0 * atr
        risk = position_size(equity, risk_cfg) if risk_cfg else 0.002
        cost = expected_cost(spread_pts)
        window = df.loc[:ts].tail(1).append(df.loc[ts:].head(10))
        hit_tp = (window["high"].max() >= tp) if side == "long" else (window["low"].min() <= tp)
        hit_sl = (window["low"].min() <= sl) if side == "long" else (window["high"].max() >= sl)
        if hit_tp and not hit_sl:
            equity *= 1 + risk * 2.0 - cost
        elif hit_sl and not hit_tp:
            equity *= 1 - risk - cost
    return pd.Series(bal_hist, index=signals.index[: len(bal_hist)])
