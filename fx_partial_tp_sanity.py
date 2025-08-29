# fx_partial_tp_sanity.py
# Simulates TP1/TP2/runner + trailing math using live MT5 bars, but DOES NOT send orders.

from __future__ import annotations
import os, argparse, time
from typing import Dict, Any
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
try:
    import MetaTrader5 as mt5
except Exception:
    mt5 = None

# --- tiny copies of helpers from your live loop ---
def mt5_init():
    if mt5 is None:
        raise RuntimeError("MetaTrader5 not installed. pip install MetaTrader5")
    path = os.getenv("MT5_PATH") or os.getenv("MTS_PATH")
    if not mt5.initialize(path=path):
        code, desc = mt5.last_error()
        raise RuntimeError(f"mt5.initialize failed: ({code}) {desc}")
    login = os.getenv("MT5_LOGIN"); pw = os.getenv("MT5_PASSWORD"); srv = os.getenv("MT5_SERVER")
    if login and pw and srv:
        if not mt5.login(int(login), password=pw, server=srv):
            code, desc = mt5.last_error()
            raise RuntimeError(f"mt5.login failed: ({code}) {desc}")
    return mt5

def ensure_symbol(symbol: str):
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"Unknown symbol {symbol}")
    if not info.visible:
        if not mt5.symbol_select(symbol, True):
            raise RuntimeError(f"symbol_select({symbol}) failed")

def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    c = df["close"]
    tr = pd.concat([
        (df["high"] - df["low"]).abs(),
        (df["high"] - c.shift()).abs(),
        (df["low"] - c.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def bars_df(symbol: str, timeframe: str, limit: int = 400) -> pd.DataFrame:
    tf_map = {"1m": mt5.TIMEFRAME_M1, "5m": mt5.TIMEFRAME_M5, "15m": mt5.TIMEFRAME_M15,
              "30m": mt5.TIMEFRAME_M30, "1h": mt5.TIMEFRAME_H1, "4h": mt5.TIMEFRAME_H4, "1d": mt5.TIMEFRAME_D1}
    tf = tf_map[timeframe.lower()]
    ensure_symbol(symbol)
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, limit)
    df = pd.DataFrame(rates)
    df.rename(columns={"time":"ts","tick_volume":"vol"}, inplace=True)
    df["timestamp"] = pd.to_datetime(df["ts"], unit="s")
    return df[["timestamp","open","high","low","close","vol"]]

def make_signal(df: pd.DataFrame, atr_mult=2.0) -> Dict[str,Any]:
    d = df.copy()
    d["ema_fast"] = ema(d["close"], 20)
    d["ema_slow"] = ema(d["close"], 50)
    d["atr"] = atr(d, 14)
    price = float(d["close"].iloc[-1]); vol = float(d["atr"].iloc[-1])
    f, s = float(d["ema_fast"].iloc[-1]), float(d["ema_slow"].iloc[-1])
    if f > s and price > f:
        sl = price - atr_mult*vol
        return {"side":"buy","price":price,"sl":sl,"tp1":price+1.5*vol,"tp2":price+3*vol,"tp3":price+5*vol}
    elif f < s and price < f:
        sl = price + atr_mult*vol
        return {"side":"sell","price":price,"sl":sl,"tp1":price-1.5*vol,"tp2":price-3*vol,"tp3":price-5*vol}
    return {"side":"flat","price":price}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--timeframe", default="5m")
    ap.add_argument("--lots", type=float, default=0.03)
    ap.add_argument("--atr_mult", type=float, default=2.0)
    ap.add_argument("--trail_mult", type=float, default=1.0)
    args = ap.parse_args()

    mt5_init()
    df = bars_df(args.symbol, args.timeframe, 400)
    sig = make_signal(df, args.atr_mult)
    px = sig["price"]; side = sig["side"]
    if side == "flat":
        print(f"[{args.symbol}] No setup right now.")
        return

    st = {
        "side": side, "lots": args.lots, "filled": 0.0,
        "entry": px, "best": px, "sl": sig["sl"],
        "tp1": sig["tp1"], "tp2": sig["tp2"], "tp3": sig["tp3"],
        "tp1_hit": False, "tp2_hit": False,
    }
    print(f"→ SIM ENTRY {side.upper()} {args.symbol} @ {px:.5f} SL {st['sl']:.5f} | TP1 {st['tp1']:.5f} TP2 {st['tp2']:.5f} TP3 {st['tp3']:.5f}")

    # walk forward using new bars; emulate pricing events
    last_ts = int(df["timestamp"].iloc[-1].timestamp())
    while True:
        time.sleep(2)
        d2 = bars_df(args.symbol, args.timeframe, 60)
        if d2.empty: continue
        now = int(d2["timestamp"].iloc[-1].timestamp())
        if now == last_ts: 
            continue
        last_ts = now

        price = float(d2["close"].iloc[-1])
        vol = float(atr(d2, 14).iloc[-1]) or 0.0
        # trail
        if st["side"] == "buy":
            st["best"] = max(st["best"], price)
            if args.trail_mult > 0 and vol > 0:
                new_sl = max(st["sl"], st["best"] - args.trail_mult * vol)
                if new_sl > st["sl"]:
                    st["sl"] = new_sl
        else:
            st["best"] = min(st["best"], price)
            if args.trail_mult > 0 and vol > 0:
                new_sl = min(st["sl"], st["best"] + args.trail_mult * vol)
                if new_sl < st["sl"]:
                    st["sl"] = new_sl

        # partials (simulated printouts only)
        part = round(st["lots"]/3.0, 2) or 0.01
        if st["side"] == "buy":
            if (not st["tp1_hit"]) and price >= st["tp1"]:
                st["tp1_hit"] = True; st["filled"] += part
                print(f"✅ TP1 @ {price:.5f} (simulate close ~1/3)")
            if (not st["tp2_hit"]) and price >= st["tp2"]:
                st["tp2_hit"] = True; st["filled"] += part
                print(f"✅ TP2 @ {price:.5f} (simulate close ~1/3)")
            if price >= st["tp3"]:
                rem = max(st["lots"] - st["filled"], 0.0)
                print(f"🏁 TP3 @ {price:.5f} (simulate close {rem:.2f}) — done")
                break
            if price <= st["sl"]:
                print(f"🛑 STOP @ {price:.5f} — done")
                break
        else:
            if (not st["tp1_hit"]) and price <= st["tp1"]:
                st["tp1_hit"] = True; st["filled"] += part
                print(f"✅ TP1 @ {price:.5f} (simulate close ~1/3)")
            if (not st["tp2_hit"]) and price <= st["tp2"]:
                st["tp2_hit"] = True; st["filled"] += part
                print(f"✅ TP2 @ {price:.5f} (simulate close ~1/3)")
            if price <= st["tp3"]:
                rem = max(st["lots"] - st["filled"], 0.0)
                print(f"🏁 TP3 @ {price:.5f} (simulate close {rem:.2f}) — done")
                break
            if price >= st["sl"]:
                print(f"🛑 STOP @ {price:.5f} — done")
                break

if __name__ == "__main__":
    main()
