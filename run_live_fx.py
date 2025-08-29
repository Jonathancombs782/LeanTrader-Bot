# run_live_fx_full.py
from __future__ import annotations
import os, time, math, argparse, datetime as dt
from typing import List, Dict, Any
import pandas as pd

from dotenv import load_dotenv
load_dotenv()

from notifier import TelegramNotifier
import charting
from loop_helpers import maybe_post_balance

# ---------- MT5 adapter ----------
try:
    import MetaTrader5 as mt5
except Exception:
    mt5 = None

def mt5_init():
    if mt5 is None:
        raise RuntimeError("MetaTrader5 package not installed. pip install MetaTrader5")

    path = os.getenv("MTS_PATH")  # e.g. C:\Program Files\OctaFX MetaTrader 5\terminal64.exe
    if not mt5.initialize(path=path):
        code, desc = mt5.last_error()
        raise RuntimeError(f"mt5.initialize failed: ({code}) {desc}")

    # Optional login if env provided
    login = os.getenv("MT5_LOGIN")
    password = os.getenv("MT5_PASSWORD")
    server = os.getenv("MT5_SERVER")
    if login and password and server:
        ok = mt5.login(int(login), password=password, server=server)
        if not ok:
            code, desc = mt5.last_error()
            raise RuntimeError(f"mt5.login failed: ({code}) {desc}")

    return mt5

# ---------- simple indicators ----------
def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def atr(df: pd.DataFrame, n: int) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat([
        (df["high"] - df["low"]).abs(),
        (df["high"] - prev).abs(),
        (df["low"] - prev).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()

# ---------- MT5 market data ----------
def mt5_bars(symbol: str, timeframe: str, limit: int = 400) -> pd.DataFrame:
    tf_map = {
        "1m": mt5.TIMEFRAME_M1, "5m": mt5.TIMEFRAME_M5, "15m": mt5.TIMEFRAME_M15,
        "30m": mt5.TIMEFRAME_M30, "1h": mt5.TIMEFRAME_H1, "4h": mt5.TIMEFRAME_H4,
        "1d": mt5.TIMEFRAME_D1,
    }
    tf = tf_map.get(timeframe.lower())
    if tf is None:
        raise ValueError(f"Unsupported timeframe for MT5: {timeframe}")

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, limit)
    if rates is None:
        code, desc = mt5.last_error()
        raise RuntimeError(f"mt5.copy_rates_from_pos failed: ({code}) {desc}")

    df = pd.DataFrame(rates)
    df.rename(columns={"time": "ts", "tick_volume": "vol"}, inplace=True)
    df["timestamp"] = pd.to_datetime(df["ts"], unit="s")
    return df[["timestamp", "open", "high", "low", "close", "vol"]]

# ---------- toy strategy (EMA trend + ATR stop) ----------
def make_signal(df: pd.DataFrame, atr_mult_stop: float = 2.0) -> Dict[str, Any]:
    d = df.copy()
    d["ema_fast"] = ema(d["close"], 20)
    d["ema_slow"] = ema(d["close"], 50)
    d["atr"] = atr(d, 14)

    long_ok = (d["ema_fast"].iloc[-1] > d["ema_slow"].iloc[-1]) and (d["close"].iloc[-1] > d["ema_fast"].iloc[-1])
    price = float(d["close"].iloc[-1])
    stop = price - atr_mult_stop * float(d["atr"].iloc[-1])

    return {
        "long": bool(long_ok),
        "price": price,
        "stop": stop,
        "score": 0.70 if long_ok else 0.30,
    }

# ---------- order helpers ----------
def mt5_market_order(symbol: str, volume: float, side: str = "buy") -> bool:
    type_map = {"buy": mt5.ORDER_TYPE_BUY, "sell": mt5.ORDER_TYPE_SELL}
    order_type = type_map[side]
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return False
    price = tick.ask if side == "buy" else tick.bid

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": order_type,
        "price": float(price),
        "deviation": 20,
        "magic": 20250825,
        "comment": "LeanTraderFX",
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    return getattr(res, "retcode", 0) == mt5.TRADE_RETCODE_DONE

# ---------- main loop ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="EURUSD,GBPUSD,XAUUSD")
    ap.add_argument("--timeframe", default="5m")
    ap.add_argument("--lots", type=float, default=0.02)
    ap.add_argument("--stake_usd", type=float, default=0)   # for ccxt loops; unused here
    ap.add_argument("--balance_every", type=int, default=60)  # seconds between Telegram portfolio posts
    ap.add_argument("--live", action="store_true", help="place real orders (MT5)")
    args = ap.parse_args()

    # init MT5 + Telegram
    mt5x = mt5_init()
    notif = TelegramNotifier()
    pairs = [p.strip().upper() for p in args.pairs.split(",")]
    notif.hello("FX (MT5)", pairs, args.timeframe)

    state = {}
    open_long: Dict[str, Dict[str, Any]] = {}

    while True:
        for sym in pairs:
            try:
                df = mt5_bars(sym, args.timeframe, limit=400)
                sig = make_signal(df)
                price, stop = sig["price"], sig["stop"]
                long_ok = sig["long"]

                # Exit rule (naive) — stop based, flat if price under stop
                if sym in open_long:
                    pos = open_long[sym]
                    if price <= pos["stop"]:
                        if args.live:
                            mt5_market_order(sym, pos["vol"], side="sell")
                        # send signal + chart when notifier enabled
                        notif.signal(sym, "EXIT", price, pos["vol"], pos["stop"],
                                     reasons=["Stop reached"], quality=0.5)
                        try:
                            if notif.enabled:
                                chart_path = None
                                try:
                                    chart_path = charting.plot_signal_chart(sym, df, entries=[{"ts": int(df['timestamp'].iloc[-1].timestamp()*1000), "price": float(df['close'].iloc[-1]), "side": "sell"}], sl=pos["stop"])
                                except Exception:
                                    chart_path = None
                                if chart_path:
                                    notif.send_photo(chart_path, caption=f"{sym} EXIT chart (tf={args.timeframe})")
                        except Exception:
                            pass
                        del open_long[sym]
                        continue

                # Entry
                if long_ok and sym not in open_long:
                    vol = float(args.lots)
                    if args.live:
                        ok = mt5_market_order(sym, vol, side="buy")
                        if not ok:
                            notif.note(f"MT5 order send failed for {sym}")
                            continue
                    open_long[sym] = {"vol": vol, "entry": price, "stop": stop}
                    reasons = [f"EMA(20)>EMA(50); ATR stop {stop:.5f}"]
                    notif.signal(sym, "BUY", price, vol, stop, reasons=reasons, quality=sig["score"])
                    try:
                        if notif.enabled:
                            chart_path = None
                            try:
                                chart_path = charting.plot_signal_chart(sym, df, entries=[{"ts": int(df['timestamp'].iloc[-1].timestamp()*1000), "price": float(df['close'].iloc[-1]), "side": "buy"}], sl=stop)
                            except Exception:
                                chart_path = None
                            if chart_path:
                                notif.send_photo(chart_path, caption=f"{sym} BUY chart (tf={args.timeframe})")
                    except Exception:
                        pass

            except Exception as e:
                notif.note(f"FX loop error {sym}: {e}")

        # Throttled portfolio post (MT5)
        state = maybe_post_balance(notif, "mt5", seconds_every=args.balance_every, state=state, prefer="mt5")
        time.sleep(5)

if __name__ == "__main__":
    main()
