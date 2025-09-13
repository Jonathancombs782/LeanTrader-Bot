"""Simple backtester: loads a model, scores a CSV, and simulates long-only trades.

This is intentionally simple: it executes at next-bar open and exits at next-bar close,
uses fixed fraction position sizing, and writes a summary to logs.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Dict

import numpy as np

from tools.featurizer import featurize_basic, load_csv


def load_model(model_path: str):
    p = Path(model_path)
    if not p.exists():
        raise FileNotFoundError(model_path)
    with p.open("rb") as f:
        data = pickle.load(f)
    # support dict or raw model
    if isinstance(data, dict) and "model" in data:
        return data["model"], data.get("meta", {})
    return data, {}


def run_backtest(model_path: str, csv_path: str, initial_cash: float = 10000.0, risk_per_trade: float = 0.01) -> Dict:
    model, meta = load_model(model_path)
    df = load_csv(csv_path)
    df = featurize_basic(df)
    # drop last row since next_close may be NaN
    df = df.reset_index(drop=True)
    # prepare features
    features = ["ret", "range", "logvol", "ma3", "ma10", "ma_diff"]
    for c in features:
        if c not in df.columns:
            df[c] = 0.0
    X = df[features].astype(float)
    # use model.predict to get labels; align with next bar
    try:
        preds = model.predict(X)
    except Exception:
        preds = np.zeros(len(X), dtype=int)

    cash = float(initial_cash)
    trades = []

    for i in range(len(df) - 1):
        pred = int(preds[i])
        cur_close = float(df.loc[i, "close"])
        next_open = float(df.loc[i + 1, "open"]) if i + 1 < len(df) else cur_close
        next_close = float(df.loc[i + 1, "close"]) if i + 1 < len(df) else cur_close
        if pred == 1:
            # open a long position sized as risk_per_trade of cash
            notional = cash * float(risk_per_trade)
            if next_open <= 0:
                continue
            size = notional / next_open
            entry_price = next_open
            exit_price = next_close
            pnl = (exit_price - entry_price) * size
            cash += pnl
            trades.append(
                {
                    "idx": i,
                    "entry": entry_price,
                    "exit": exit_price,
                    "size": size,
                    "pnl": pnl,
                    "cash": cash,
                }
            )

    total_pnl = cash - initial_cash
    wins = sum(1 for t in trades if t["pnl"] > 0)
    losses = sum(1 for t in trades if t["pnl"] <= 0)
    return {
        "model": model_path,
        "meta": meta,
        "n_trades": len(trades),
        "wins": wins,
        "losses": losses,
        "initial_cash": initial_cash,
        "final_cash": cash,
        "total_pnl": total_pnl,
        "trades": trades[:20],
    }
