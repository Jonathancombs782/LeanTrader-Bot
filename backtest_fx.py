
import argparse, os, datetime
import pandas as pd, numpy as np, yfinance as yf, matplotlib.pyplot as plt
from utils import setup_logger, ensure_dir, bps_to_frac
from strategy import TrendBreakoutStrategy
from risk import RiskConfig
from forex_utils import pip_size

def yf_symbol(pair: str) -> str:
    pair = pair.upper().replace('/','')
    return f"{pair}=X"

def load_yf_ohlcv(pair: str, interval: str = "15m", start: str = "2024-01-01"):
    sym = yf_symbol(pair)
    df = yf.download(sym, interval=interval, start=start, progress=False)
    df = df.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
    df = df.reset_index().rename(columns={"Datetime":"timestamp","Date":"timestamp"})
    return df[["timestamp","open","high","low","close","volume"]]

def run(symbols: list, timeframe: str, since: str, out_dir: str = "reports"):
    log = setup_logger("backtest_fx")
    ensure_dir(out_dir)

    # Map timeframe to yfinance interval
    tf_map = {"1m":"1m","5m":"5m","15m":"15m","1h":"60m"}
    interval = tf_map.get(timeframe, "15m")

    curve = []
    equity = 10000.0
    fee_frac = bps_to_frac(1)

    strat = TrendBreakoutStrategy()

    for s in symbols:
        df = load_yf_ohlcv(s, interval=interval, start=since)
        df = df.dropna().reset_index(drop=True)
        d, _ = strat.entries_and_exits(df)
        in_pos = False; entry = 0.0

        for i in range(len(d)):
            price = d.loc[i,"close"]
            if not in_pos and d.loc[i,"long_signal"]:
                entry = price
                in_pos = True
                equity -= entry * fee_frac
            elif in_pos:
                atr = d.loc[i,"atr"]
                trail = max(entry - 1.2*atr, price - 1.2*atr)
                if price <= trail:
                    pnl = price - entry - price*fee_frac - entry*fee_frac
                    equity += price + pnl
                    in_pos = False
            curve.append(equity)

    plt.figure(figsize=(10,5))
    plt.plot(curve)
    plt.title("FX Backtest Equity (Approx)")
    plt.xlabel("Bars"); plt.ylabel("Equity ($)")
    path = os.path.join(out_dir, "equity_fx.png")
    plt.savefig(path, bbox_inches="tight")
    print(f"Saved: {path}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="EURUSD,GBPUSD,USDJPY")
    ap.add_argument("--timeframe", default="15m")
    ap.add_argument("--since", default="2024-01-01")
    args = ap.parse_args()
    run([s.strip() for s in args.symbols.split(",")], args.timeframe, args.since)
