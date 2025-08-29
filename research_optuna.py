# research_optuna.py
from __future__ import annotations
import os, json, time
from pathlib import Path
import pandas as pd
import optuna

# our strategies
from strategy import TrendBreakoutStrategy, NakedForexStrategy

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
DATA_PATH = DATA_DIR / "history.csv"
BEST_PATH = ROOT / "reports" / "best_params.json"
BEST_PATH.parent.mkdir(parents=True, exist_ok=True)

# ------------ history helpers ------------
def build_history_ccxt(exchange_id: str, symbol: str, timeframe: str, lookback_days: int = 30) -> pd.DataFrame:
    """
    Pull OHLCV from a CCXT crypto exchange and write data/history.csv with
    columns: timestamp,open,high,low,close,vol
    """
    from router import ExchangeRouter
    ex = ExchangeRouter()
    ms_now = int(time.time() * 1000)
    ms_back = lookback_days * 24 * 60 * 60 * 1000
    since = ms_now - ms_back
    all_rows = []

    while True:
        batch = ex.safe_fetch_ohlcv(symbol, timeframe=timeframe, limit=1000)
        if not batch:
            break
        all_rows += batch
        since = batch[-1][0] + 60_000
        if len(batch) < 1000:
            break
        time.sleep(0.2)

    if not all_rows:
        raise RuntimeError("No candles returned from exchange.")

    df = pd.DataFrame(all_rows, columns=["ts","open","high","low","close","vol"])
    df["timestamp"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    out = df[["timestamp","open","high","low","close","vol"]]
    out.to_csv(DATA_PATH, index=False)
    return out

def ensure_history() -> pd.DataFrame:
    """
    Make sure data/history.csv exists. If missing, auto-fetch using CCXT.
    Environment:
      EXCHANGE_ID (default binanceus)
      OPT_SYMBOL  (default DOGE/USD)
      TIMEFRAME   (default 1m)
      OPT_LOOKBACK_DAYS (default 30)
    """
    if DATA_PATH.exists():
        df = pd.read_csv(DATA_PATH)
        if len(df) >= 200:
            return df
    # build if missing or too small
    ex_id = os.getenv("EXCHANGE_ID", "binanceus")
    symbol = os.getenv("OPT_SYMBOL", os.getenv("SYMBOLS", "DOGE/USD").split(",")[0].strip())
    timeframe = os.getenv("TIMEFRAME", "1m")
    lookback_days = int(os.getenv("OPT_LOOKBACK_DAYS", "30"))
    print(f"[optuna] building history via CCXT: {ex_id} {symbol} {timeframe} {lookback_days}d")
    return build_history_ccxt(ex_id, symbol, timeframe, lookback_days)

# ------------ scoring ------------
def score_equity(d: pd.DataFrame) -> float:
    # robust guards so Optuna never crashes
    if d is None or d.empty or ("close" not in d) or ("long_signal" not in d):
        return -999.0
    sig = d["long_signal"].astype(bool).shift(1).fillna(False)
    ret = pd.Series(d["close"]).pct_change().fillna(0.0)
    eq = (sig * ret).cumsum()
    if eq.empty or pd.isna(eq.iloc[-1]):
        return -999.0
    return float(eq.iloc[-1])

# ------------ search space ------------
def make_strategy(trial):
    choice = trial.suggest_categorical("strategy", ["trend", "naked"])
    if choice == "trend":
        params = {
            "ema_fast": trial.suggest_int("ema_fast", 10, 80),
            "ema_slow": trial.suggest_int("ema_slow", 100, 400),
            "bb_period": trial.suggest_int("bb_period", 10, 40),
            "bb_std": trial.suggest_float("bb_std", 1.5, 3.0),
            "bb_bw_lookback": trial.suggest_int("bb_bw_lookback", 60, 200),
            "bb_bw_quantile": trial.suggest_float("bb_bw_quantile", 0.3, 0.8),
            "atr_period": trial.suggest_int("atr_period", 10, 20),
        }
        strat = TrendBreakoutStrategy(**params)
    else:
        params = {
            "sr_lookback": trial.suggest_int("sr_lookback", 40, 120),
            "pin_len_mult": trial.suggest_float("pin_len_mult", 1.2, 2.2),
            "engulf_body_mult": trial.suggest_float("engulf_body_mult", 1.0, 1.8),
            "atr_period": trial.suggest_int("atr_period", 10, 20),
        }
        strat = NakedForexStrategy(**params)

    risk = {
        "atr_stop_mult": trial.suggest_float("atr_stop_mult", 1.0, 3.5),
        "atr_trail_mult": trial.suggest_float("atr_trail_mult", 1.0, 3.0),
    }
    return choice, strat, params, risk

# ------------ objective ------------
def objective(trial):
    df = ensure_history()
    choice, strat, params, risk = make_strategy(trial)
    d, _ = strat.entries_and_exits(
        df, atr_stop_mult=risk["atr_stop_mult"], atr_trail_mult=risk["atr_trail_mult"]
    )
    return score_equity(d)

def main():
    trials = int(os.getenv("OPTUNA_TRIALS", "50"))
    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=trials)

    best = study.best_params
    strat_name = best.pop("strategy")
    params = {k: v for k, v in best.items() if k not in ("atr_stop_mult","atr_trail_mult")}
    risk = {k: best[k] for k in ("atr_stop_mult","atr_trail_mult") if k in best}

    payload = {"strategy": strat_name, "params": params, "risk": risk, "score": study.best_value}
    with open(BEST_PATH, "w") as f:
        json.dump(payload, f, indent=2)
    print("Saved", BEST_PATH, "=>", payload)

if __name__ == "__main__":
    main()
