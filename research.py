# research_optuna.py
from __future__ import annotations

import os, json, time, math, argparse
from pathlib import Path
from typing import Dict, Any, List, Tuple

import numpy as np
import pandas as pd
import optuna
from optuna.pruners import MedianPruner

import ccxt

from strategy_zoo import get_strategy, REGISTRY
from data_sources import (
    merge_externals,
    EconomicCalendarSource,
    NewsSentimentSource,
    OnchainMetricSource,
    FundingRateSource,
)

REPORTS = Path("reports")
REPORTS.mkdir(exist_ok=True)

# --------------------- data utils ---------------------
def fetch_ohlcv_range(ex, symbol: str, timeframe: str, start_ms: int, end_ms: int, limit=1000) -> pd.DataFrame:
    all_rows = []
    since = start_ms
    tf_sec = ex.parse_timeframe(timeframe)
    while True:
        # prefer router safe wrapper when available, but guard both calls
        rows = []
        try:
            if hasattr(ex, 'safe_fetch_ohlcv'):
                try:
                    rows = ex.safe_fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)  # type: ignore[arg-type]
                except Exception as e:
                    print(f"[research] safe_fetch_ohlcv failed for {symbol}: {e}")
                    rows = []
            else:
                try:
                    rows = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
                except Exception as e:
                    print(f"[research] fetch_ohlcv failed for {symbol}: {e}")
                    # last resort: try router-style helper if present
                    try:
                        rows = ex.safe_fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)  # type: ignore[arg-type]
                    except Exception:
                        rows = []
        except Exception as e:
            print(f"[research] unexpected fetch error for {symbol}: {e}")
            rows = []
        if not rows:
            break
        all_rows.extend(rows)
        last_ts = rows[-1][0]
        if last_ts >= end_ms or len(rows) < limit:
            break
        since = last_ts + tf_sec * 1000
        time.sleep(getattr(ex, "rateLimit", 200) / 1000.0)
    df = pd.DataFrame(all_rows, columns=["ts","open","high","low","close","vol"]).drop_duplicates("ts")
    df["timestamp"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df

def build_rolling_windows(df: pd.DataFrame, train_days=30, test_days=7, step_days=7) -> List[Tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    if df.empty:
        return []
    start = df["timestamp"].min().normalize()
    end   = df["timestamp"].max().normalize()
    one_day = pd.Timedelta(days=1)

    windows = []
    cur_train_start = start
    while True:
        tr_start = cur_train_start
        tr_end   = tr_start + pd.Timedelta(days=train_days) - one_day
        te_start = tr_end + one_day
        te_end   = te_start + pd.Timedelta(days=test_days) - one_day
        if te_end > end:
            break
        windows.append((tr_start, tr_end, te_start, te_end))
        cur_train_start = cur_train_start + pd.Timedelta(days=step_days)
    return windows

# --------------------- regime/session features ---------------------
def add_session_cols(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    utc_hour = d["timestamp"].dt.hour
    d["tokyo"]  = ((utc_hour >= 0)  & (utc_hour < 9)).astype(int)
    d["london"] = ((utc_hour >= 7)  & (utc_hour < 16)).astype(int)
    d["ny"]     = ((utc_hour >= 12) & (utc_hour < 21)).astype(int)
    return d

def add_regime_cols(df: pd.DataFrame, vol_n=60) -> pd.DataFrame:
    d = df.copy()
    ret = d["close"].pct_change()
    d["rv"] = (ret.rolling(vol_n).std(ddof=0) * np.sqrt(60)).fillna(0)
    d["high_vol"] = (d["rv"] > d["rv"].rolling(1000, min_periods=10).median()).astype(int)
    return d

# --------------------- guards / scoring ---------------------
def simple_backtest_long_only(d: pd.DataFrame, fee_bps=10, slip_bps=3, atr_stop_mult=2.0) -> Dict[str, float]:
    fee = fee_bps/10000.0
    slip = slip_bps/10000.0
    c = d["close"].values
    sig = d["long_signal"].fillna(False).values
    atr = d.get("atr", pd.Series(np.zeros(len(d)), index=d.index)).fillna(0).values

    pos = 0
    entry = 0.0
    trade_pnls = []
    for i in range(1, len(c)):
        px = c[i]
        if pos == 0 and sig[i-1]:
            entry = c[i] * (1 + slip + fee)
            pos = 1
        elif pos == 1:
            stop = entry - atr_stop_mult * atr[i]
            exit_now = False
            if px <= stop:
                exit_now = True
            elif not sig[i-1]:
                exit_now = True
            if exit_now:
                exitp = px * (1 - slip - fee)
                trade_pnls.append(exitp - entry)
                pos = 0

    ret = pd.Series(np.zeros(len(c)), index=d.index)
    ret.iloc[1:] = np.diff(c) / np.maximum(c[:-1], 1e-12)
    max_dd = float((ret.cumsum().cummax() - ret.cumsum()).max())
    sharpe = float((ret.mean() / (ret.std() + 1e-12)) * math.sqrt(365*24*60)) if ret.std() > 0 else 0.0
    return {"trades": int(len(trade_pnls)), "pnl_sum": float(np.sum(trade_pnls) if trade_pnls else 0.0),
            "pnl_avg": float(np.mean(trade_pnls) if trade_pnls else 0.0), "max_dd": max_dd, "sharpe": sharpe,
            "ret_sum": float(ret.sum())}

def score_metrics(m: Dict[str,float]) -> float:
    # higher is better; penalize drawdown
    return m["sharpe"] - 3.0 * m["max_dd"]

# --------------------- Optuna objective ---------------------
def make_objective(
    full_df: pd.DataFrame, strategy_name: str,
    fee_bps: int, slip_bps: int,
    train_days: int, test_days: int, step_days: int,
):
    windows = build_rolling_windows(full_df, train_days=train_days, test_days=test_days, step_days=step_days)
    if not windows:
        raise RuntimeError("Not enough data to build rolling windows. Increase date range or reduce windows.")

    def sample_params(trial: optuna.Trial) -> Dict[str, Any]:
        if strategy_name == "ema_bb_squeeze":
            return dict(
                ema_fast = trial.suggest_int("ema_fast", 5, 30),
                ema_slow = trial.suggest_int("ema_slow", 20, 80),
                bb_n     = trial.suggest_int("bb_n", 14, 40),
                bb_k     = trial.suggest_float("bb_k", 1.5, 3.0),
                bw_q     = trial.suggest_float("bw_q", 0.1, 0.5),
            )
        elif strategy_name == "rsi_meanrev":
            return dict(
                rsi_n  = trial.suggest_int("rsi_n", 8, 30),
                buy_th = trial.suggest_int("buy_th", 15, 40),
                exit_th= trial.suggest_int("exit_th", 45, 65),
                min_atr= trial.suggest_float("min_atr", 0.0, 0.05),
            )
        elif strategy_name == "donchian_breakout":
            return dict(
                ch_n = trial.suggest_int("ch_n", 10, 60),
                atr_n= trial.suggest_int("atr_n", 10, 30),
            )
        elif strategy_name == "ma_pullback":
            return dict(
                ma_n = trial.suggest_int("ma_n", 20, 120),
                z_n  = trial.suggest_int("z_n", 30, 150),
                z_th = trial.suggest_float("z_th", -2.5, -0.5),
            )
        else:  # evo_combo
            return dict(seed=trial.suggest_int("seed", 0, 10000))

    def objective(trial: optuna.Trial) -> float:
        params = sample_params(trial)
        strat = get_strategy(strategy_name)

        # Try to set attributes if present
        for k, v in params.items():
            if hasattr(strat, k):
                try: setattr(strat, k, v)
                except Exception: pass

        def sig_fun(dfX: pd.DataFrame) -> pd.DataFrame:
            dfX = add_session_cols(dfX)
            dfX = add_regime_cols(dfX)
            dfX = merge_externals(
                dfX,
                calendar=EconomicCalendarSource(path="data/calendar.csv", high_only=True, pre_minutes=30, post_minutes=30),
                news=NewsSentimentSource(path="data/news_sentiment.csv", symbol=None),
                onchain=OnchainMetricSource(path="data/onchain.csv", metric="active_addresses"),
                funding=FundingRateSource(path="data/funding.csv", symbol=None),
            )
            if hasattr(strat, "entries_and_exits"):
                d, _ = strat.entries_and_exits(dfX, atr_stop_mult=2.0, atr_trail_mult=1.3)
            else:
                d = strat.apply(dfX, **params)
                if "long_signal" not in d.columns:
                    d["long_signal"] = False
                if "atr" not in d.columns:
                    high, low, close = d["high"], d["low"], d["close"]
                    prev_close = close.shift(1)
                    tr = pd.concat(
                        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
                        axis=1,
                    ).max(axis=1)
                    d["atr"] = tr.rolling(14).mean()
            return d

        scores = []
        for step_idx, (tr_s, tr_e, te_s, te_e) in enumerate(windows, start=1):
            tr = full_df[(full_df["timestamp"] >= tr_s) & (full_df["timestamp"] <= tr_e)].copy()
            te = full_df[(full_df["timestamp"] >= te_s) & (full_df["timestamp"] <= te_e)].copy()
            if len(tr) < 200 or len(te) < 100:
                continue
            d_tr = sig_fun(tr); m_tr = simple_backtest_long_only(d_tr, fee_bps=fee_bps, slip_bps=slip_bps)
            d_te = sig_fun(te); m_te = simple_backtest_long_only(d_te, fee_bps=fee_bps, slip_bps=slip_bps)
            s = score_metrics(m_te); scores.append(s)
            trial.report(float(np.nanmean(scores)), step=step_idx)
            if trial.should_prune():
                raise optuna.TrialPruned()

        if not scores:
            return -1e9
        return float(np.nanmean(scores))

    return objective

# --------------------- top-level ---------------------
def optimize_symbol(ex, symbol: str, timeframe: str, start: str, end: str,
                    fee_bps: int, slip_bps: int,
                    train_days=30, test_days=7, step_days=7,
                    trials_per_strategy=40, seed=42) -> Dict[str, Any]:
    start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    end_ms   = int(pd.Timestamp(end,   tz="UTC").timestamp() * 1000)
    df = fetch_ohlcv_range(ex, symbol, timeframe, start_ms, end_ms)
    if len(df) < 500:
        raise RuntimeError(f"Not enough candles for {symbol} in selected range.")

    best_overall = None
    for sname in REGISTRY.keys():
        study = optuna.create_study(direction="maximize", pruner=MedianPruner(n_warmup_steps=4))
        obj = make_objective(
            df, sname, fee_bps, slip_bps,
            train_days=train_days, test_days=test_days, step_days=step_days,
        )
        study.optimize(obj, n_trials=trials_per_strategy, n_jobs=1, show_progress_bar=False, gc_after_trial=True)
        top = study.best_trial
        artifact = {
            "strategy": sname,
            "params": top.params,
            "score": float(top.value),
            "symbol": symbol,
            "timeframe": timeframe,
            "meta": {"trials": len(study.trials)},
        }
        if (best_overall is None) or (artifact["score"] > best_overall["score"]):
            best_overall = artifact

        pd.DataFrame([{
            **t.params, "value": t.value, "state": str(t.state), "number": t.number
        } for t in study.trials]).to_csv(REPORTS / f"{symbol.replace('/','_')}_{sname}_optuna.csv", index=False)

    assert best_overall is not None
    return best_overall

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exchange", default="binanceus")
    ap.add_argument("--symbols", default="DOGE/USD")
    ap.add_argument("--timeframe", default="1m")
    ap.add_argument("--start", required=True)  # e.g. 2025-07-01
    ap.add_argument("--end",   required=True)  # e.g. 2025-08-24
    ap.add_argument("--fee_bps", type=int, default=10)
    ap.add_argument("--slip_bps", type=int, default=3)
    ap.add_argument("--train_days", type=int, default=30)
    ap.add_argument("--test_days",  type=int, default=7)
    ap.add_argument("--step_days",  type=int, default=7)
    ap.add_argument("--trials", type=int, default=60)  # per strategy
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    ex = getattr(ccxt, args.exchange)({"enableRateLimit": True})
    best_across = []
    for sym in [s.strip() for s in args.symbols.split(",") if s.strip()]:
        print(f"=== Optimizing {sym} ===")
        best = optimize_symbol(
            ex, sym, args.timeframe, args.start, args.end,
            fee_bps=args.fee_bps, slip_bps=args.slip_bps,
            train_days=args.train_days, test_days=args.test_days, step_days=args.step_days,
            trials_per_strategy=args.trials, seed=args.seed
        )
        best["exchange"] = args.exchange
        best_across.append(best)

    best_across.sort(key=lambda x: x["score"], reverse=True)
    winner = best_across[0]
    out = {
        "exchange": winner["exchange"],
        "symbol": winner["symbol"],
        "timeframe": winner["timeframe"],
        "strategy": winner["strategy"],
        "params": winner["params"],
        "score": winner["score"],
    }
    with open(REPORTS / "best_params.json", "w") as f:
        json.dump(out, f, indent=2, default=float)
    print("Saved:", REPORTS / "best_params.json")
    print("Best:", out)

if __name__ == "__main__":
    main()
