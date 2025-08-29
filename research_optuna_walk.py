# research_optuna_walk.py
from __future__ import annotations
import os, json, math, time, argparse, datetime as dt
from pathlib import Path
from typing import Dict, Any, Tuple, List

import numpy as np
import pandas as pd
import optuna

PROJECT_ROOT = Path(__file__).resolve().parent
REPORTS = PROJECT_ROOT / "reports"
REPORTS.mkdir(exist_ok=True)

from strategy import TrendBreakoutStrategy
from utils import bps_to_frac
from news_service import harvest_rss, build_clean  # keep our store fresh

def fetch_history_ccxt(exchange_id: str, symbol: str, timeframe: str, days: int = 60) -> pd.DataFrame:
    from router import ExchangeRouter
    ex = ExchangeRouter()
    ms = int(days * 24 * 60 * 60 * 1000)
    now = int(time.time()*1000)
    since = now - ms
    out: List[List[float]] = []
    while since < now:
        try:
            batch = ex.safe_fetch_ohlcv(symbol, timeframe=timeframe, limit=1000)
            if not batch: break
            out.extend(batch)
            since = int(batch[-1][0]) + 1
            if len(out) > 10000: break
        except Exception:
            break
    if not out: 
        raise RuntimeError("no data")
    df = pd.DataFrame(out, columns=["ts","open","high","low","close","vol"])
    df["timestamp"] = pd.to_datetime(df["ts"], unit="ms")
    return df

def simulate(df: pd.DataFrame, params: Dict[str, Any]) -> Tuple[float,float,int]:
    """Simple long-only sim with ATR stop + trail; return (ret, sharpe, trades)."""
    strat = TrendBreakoutStrategy(
        ema_fast=params["ema_fast"], ema_slow=params["ema_slow"],
        bb_period=params["bb_period"], bb_std=params["bb_std"],
        bb_bw_lookback=params["bb_bw_lookback"], bb_bw_quantile=params["bb_bw_quantile"],
        atr_period=params["atr_period"]
    )
    d, _info = strat.entries_and_exits(
        df[["timestamp","open","high","low","close","vol"]],
        atr_stop_mult=params["atr_stop_mult"],
        atr_trail_mult=params["atr_trail_mult"],
    )
    c = d["close"].astype(float).to_numpy()
    atr = d["atr"].astype(float).fillna(0.0).to_numpy()
    long_sig = d["long_signal"].fillna(False).to_numpy()

    pos = 0.0; entry = 0.0; stop = 0.0
    rets = []
    for i in range(len(c)):
        price = c[i]; a = atr[i]
        # trailing update
        if pos > 0:
            stop = max(stop, price - params["atr_trail_mult"]*a)
            if price <= stop:
                pnl = (price - entry) / entry
                rets.append(pnl)
                pos = 0.0
                continue
        # entry
        if pos == 0.0 and long_sig[i]:
            pos = 1.0
            entry = price
            stop  = entry - params["atr_stop_mult"]*a

    total_ret = float(np.nansum(rets))
    if len(rets) == 0:
        return total_ret, 0.0, 0
    sharpe = float(np.nanmean(rets) / (np.nanstd(rets)+1e-9) * math.sqrt(252*24*60))  # rough scale
    return total_ret, sharpe, len(rets)

def walk_forward_optimize(df: pd.DataFrame, train_days=30, test_days=7, n_trials=50) -> Dict[str,Any]:
    # Split into rolling windows; optimize on train, evaluate on test.
    windows = []
    ts = df["timestamp"]
    start = ts.min().normalize()
    end   = ts.max()
    while start + pd.Timedelta(days=train_days+test_days) < end:
        t0 = start
        t1 = t0 + pd.Timedelta(days=train_days)
        t2 = t1 + pd.Timedelta(days=test_days)
        windows.append((t0,t1,t2))
        start = start + pd.Timedelta(days=test_days)

    results = []
    for (t0,t1,t2) in windows:
        train = df[(df["timestamp"]>=t0) & (df["timestamp"]<t1)].reset_index(drop=True)
        test  = df[(df["timestamp"]>=t1) & (df["timestamp"]<t2)].reset_index(drop=True)
        if len(train) < 300 or len(test) < 200:
            continue

        def objective(trial: optuna.Trial):
            params = {
                "ema_fast": trial.suggest_int("ema_fast", 10, 120),
                "ema_slow": trial.suggest_int("ema_slow", 40, 300),
                "bb_period": trial.suggest_int("bb_period", 14, 40),
                "bb_std": trial.suggest_float("bb_std", 1.6, 3.2),
                "bb_bw_lookback": trial.suggest_int("bb_bw_lookback", 60, 250),
                "bb_bw_quantile": trial.suggest_float("bb_bw_quantile", 0.2, 0.9),
                "atr_period": trial.suggest_int("atr_period", 10, 24),
                "atr_stop_mult": trial.suggest_float("atr_stop_mult", 1.2, 3.2),
                "atr_trail_mult": trial.suggest_float("atr_trail_mult", 1.0, 2.8),
            }
            r, s, n = simulate(train, params)
            # prefer more robust: Sharpe + small trade count bonus
            return s + min(n, 10) * 0.01

        study = optuna.create_study(direction="maximize")
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
        best = study.best_params
        r_test, s_test, n_test = simulate(test, best)
        results.append({"params":best, "score":s_test, "r":r_test, "n":n_test})

    if not results:
        raise RuntimeError("walk_forward_optimize: no windows produced results")

    # choose median-best by score
    scores = [x["score"] for x in results]
    mid = float(np.median(scores))
    pick = min(results, key=lambda x: abs(x["score"]-mid))

    payload = {
        "strategy": "trend",
        "params": {
            "ema_fast": pick["params"]["ema_fast"],
            "ema_slow": pick["params"]["ema_slow"],
            "bb_period": pick["params"]["bb_period"],
            "bb_std": pick["params"]["bb_std"],
            "bb_bw_lookback": pick["params"]["bb_bw_lookback"],
            "bb_bw_quantile": pick["params"]["bb_bw_quantile"],
            "atr_period": pick["params"]["atr_period"],
        },
        "risk": {
            "atr_stop_mult": pick["params"]["atr_stop_mult"],
            "atr_trail_mult": pick["params"]["atr_trail_mult"],
        },
        "score": float(pick["score"]),
    }
    (REPORTS / "best_params.json").write_text(json.dumps(payload, indent=2))
    return payload

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exchange", default=os.getenv("EXCHANGE_ID","binanceus"))
    ap.add_argument("--symbol",   default=os.getenv("OPT_SYMBOL","DOGE/USD"))
    ap.add_argument("--timeframe", default="1m")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--train_days", type=int, default=30)
    ap.add_argument("--test_days", type=int, default=7)
    ap.add_argument("--trials", type=int, default=50)
    args = ap.parse_args()

    # keep news cache fresh (optional; also proves internet access works from scheduler)
    try:
        harvest_rss()
        build_clean()
    except Exception:
        pass

    df = fetch_history_ccxt(args.exchange, args.symbol, args.timeframe, days=args.days)
    payload = walk_forward_optimize(df, train_days=args.train_days, test_days=args.test_days, n_trials=args.trials)
    print("Saved", REPORTS / "best_params.json", "=>", payload)

if __name__ == "__main__":
    main()
