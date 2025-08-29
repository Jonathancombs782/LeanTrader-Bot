
import argparse, os, time, math, pandas as pd
from dotenv import load_dotenv
from utils import setup_logger, bps_to_frac
from strategy import TrendBreakoutStrategy
from guardrails import GuardConfig, TradeGuard
from brokers.broker_oanda import OandaBroker
from forex_utils import pip_size, pip_value_per_unit, units_for_risk

def paper_oanda(pairs: list, timeframe: str, fixed_risk_usd: float):
    load_dotenv()
    log = setup_logger("paper_fx_oanda")
    brk = OandaBroker()
    strat = TrendBreakoutStrategy()
    guard = TradeGuard(GuardConfig())

    positions = {}

    while True:
        for sym in pairs:
            try:
                if hasattr(brk, 'safe_fetch_ohlcv'):
                    rows = brk.safe_fetch_ohlcv(sym, timeframe=timeframe, limit=400)
                else:
                    rows = brk.fetch_ohlcv(sym, timeframe=timeframe, limit=400)
            except Exception as e:
                print(f"[paper_fx_oanda] fetch_ohlcv failed for {sym}: {e}")
                rows = []
            df = pd.DataFrame(rows, columns=["ts","open","high","low","close","vol"])
            d, _ = strat.entries_and_exits(df.rename(columns={"ts":"timestamp"}))

            price = float(d["close"].iloc[-1])
            atr = float(d["atr"].iloc[-1]) if not math.isnan(d["atr"].iloc[-1]) else 0.0
            pv_unit = pip_value_per_unit(sym, quote_to_usd=1.0)
            atr_pips = atr / pip_size(sym)
            units = units_for_risk(fixed_risk_usd, atr_pips, pv_unit)

            guard.on_new_bar()

            if sym not in positions and d["long_signal"].iloc[-1]:
                positions[sym] = {"entry": price, "units": units, "stop": price - 2.0*atr}
                log.info(f"[PAPER OANDA] ENTER {sym} units={units:.0f} price={price:.5f} stop={price-2*atr:.5f}")
            elif sym in positions:
                pos = positions[sym]
                pos["stop"] = max(pos["stop"], price - 1.2*atr)
                if price <= pos["stop"]:
                    pnl = (price - pos["entry"]) * pos["units"]
                    log.info(f"[PAPER OANDA] EXIT {sym} pnl={pnl:.2f}")
                    del positions[sym]
        time.sleep(5)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="EUR/USD,GBP/USD,USD/JPY")
    ap.add_argument("--timeframe", default="5m")
    ap.add_argument("--risk_usd", type=float, default=5.0)
    args = ap.parse_args()
    pairs = [s.strip() for s in args.pairs.split(",")]
    paper_oanda(pairs, args.timeframe, args.risk_usd)
