# run_live_fx_full.py
from __future__ import annotations

import os, time, argparse
from typing import Dict, Any, Optional
from datetime import datetime, timezone

import pandas as pd
from dotenv import load_dotenv
load_dotenv()

from news_adapter import fx_guard_for_symbol  # NEW
import charting

# --- Telegram (minimal) ---
try:
    from notifier import TelegramNotifier
except Exception:
    class TelegramNotifier:
        def hello(self, label: str, pairs, tf): print(f"[TG] Hello {label} {pairs} tf={tf}")
        def signal(self, sym, side, price, lots, sl, reasons=None, quality=0.7): print(f"[TG] {sym} {side} {price} lots={lots} sl={sl} reasons={reasons}")
        def note(self, msg): print("[TG]", msg)
        def daily_pnl(self, msg): print("[TG] PnL", msg)

# --- MT5 setup ---
try:
    import MetaTrader5 as mt5
except Exception:
    mt5 = None

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

# --- indicators ---
def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    c = df["close"]
    tr = pd.concat([
        (df["high"] - df["low"]).abs(),
        (df["high"] - c.shift()).abs(),
        (df["low"] - c.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean().ffill()  # fix deprecation

def bars_df(symbol: str, timeframe: str, limit: int = 400) -> pd.DataFrame:
    tf_map = {
        "1m": mt5.TIMEFRAME_M1, "5m": mt5.TIMEFRAME_M5, "15m": mt5.TIMEFRAME_M15,
        "30m": mt5.TIMEFRAME_M30, "1h": mt5.TIMEFRAME_H1, "4h": mt5.TIMEFRAME_H4, "1d": mt5.TIMEFRAME_D1
    }
    tf = tf_map.get(timeframe.lower())
    ensure_symbol(symbol)
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, limit)
    df = pd.DataFrame(rates)
    df.rename(columns={"time":"ts","tick_volume":"vol"}, inplace=True)
    df["timestamp"] = pd.to_datetime(df["ts"], unit="s")
    return df[["timestamp","open","high","low","close","vol"]]

# --- signal ---
def make_signal(df: pd.DataFrame, atr_mult: float = 2.0) -> Dict[str, Any]:
    d = df.copy()
    d["ema_fast"] = ema(d["close"], 20)
    d["ema_slow"] = ema(d["close"], 50)
    d["atr"] = atr(d, 14)

    price = float(d["close"].iloc[-1]); vol = float(d["atr"].iloc[-1])
    fast, slow = float(d["ema_fast"].iloc[-1]), float(d["ema_slow"].iloc[-1])

    if fast > slow and price > fast:
        sl = price - atr_mult*vol
        return {"side":"buy","price":price,"sl":sl,
                "tp1":price+1.5*vol, "tp2":price+3.0*vol, "tp3":price+5.0*vol,
                "reasons":["EMA20>EMA50","close>EMA20"], "score":0.70}
    if fast < slow and price < fast:
        sl = price + atr_mult*vol
        return {"side":"sell","price":price,"sl":sl,
                "tp1":price-1.5*vol, "tp2":price-3.0*vol, "tp3":price-5.0*vol,
                "reasons":["EMA20<EMA50","close<EMA20"], "score":0.68}
    return {"side":"flat","price":price}

# --- order helpers ---
def _tick_price(symbol: str, side: str) -> Optional[float]:
    t = mt5.symbol_info_tick(symbol)
    if not t: return None
    return float(t.ask if side=="buy" else t.bid)

def market_open(symbol: str, side: str, lots: float, sl: float) -> Dict[str, Any]:
    side = side.lower()
    price = _tick_price(symbol, side)
    if price is None:
        return {"ok": False, "comment": "no tick"}
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "type": mt5.ORDER_TYPE_BUY if side=="buy" else mt5.ORDER_TYPE_SELL,
        "volume": float(lots),
        "price": float(price),
        "deviation": 20,
        "sl": float(sl),
        "type_filling": mt5.ORDER_FILLING_IOC,
        "magic": 90210,
        "comment": "LeanFX_OPEN",
    }
    r = mt5.order_send(req)
    return {"ok": bool(r and r.retcode == mt5.TRADE_RETCODE_DONE), "retcode":getattr(r,"retcode",-1), "comment":getattr(r,"comment","")}

def market_reduce(symbol: str, side_open: str, lots: float) -> Dict[str, Any]:
    side = "sell" if side_open=="buy" else "buy"
    price = _tick_price(symbol, side)
    if price is None:
        return {"ok": False, "comment": "no tick"}
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "type": mt5.ORDER_TYPE_BUY if side=="buy" else mt5.ORDER_TYPE_SELL,
        "volume": float(lots),
        "price": float(price),
        "deviation": 20,
        "type_filling": mt5.ORDER_FILLING_IOC,
        "magic": 90211,
        "comment": "LeanFX_REDUCE",
    }
    r = mt5.order_send(req)
    return {"ok": bool(r and r.retcode == mt5.TRADE_RETCODE_DONE), "retcode":getattr(r,"retcode",-1)}

def modify_sl(symbol: str, sl: float) -> bool:
    poss = mt5.positions_get(symbol=symbol)
    if not poss: return False
    pos = poss[0]
    req = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": symbol,
        "position": pos.ticket,
        "sl": float(sl),
        "tp": float(pos.tp or 0.0),
        "magic": 90212,
        "comment": "LeanFX_MOD_SL",
    }
    r = mt5.order_send(req)
    return bool(r and r.retcode == mt5.TRADE_RETCODE_DONE)

# --- loop ---
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="EURUSD,GBPUSD,XAUUSD")
    ap.add_argument("--timeframe", default="5m")
    ap.add_argument("--lots", type=float, default=0.03)
    ap.add_argument("--atr_mult", type=float, default=2.0)
    ap.add_argument("--trail_mult", type=float, default=1.0)
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()

    mt5_init()
    notif = TelegramNotifier()
    pairs = [p.strip().upper() for p in args.pairs.split(",")]
    notif.hello("Live FX (MT5)", pairs, args.timeframe)

    open_pos: Dict[str, Dict[str, Any]] = {}
    last_daily = ""

    while True:
        for sym in pairs:
            try:
                guard = fx_guard_for_symbol(sym, hard_block_min=10, soft_bias_min=120)
                if guard["avoid_until"] and time.time() < guard["avoid_until"]:
                    # news hard block
                    notif.note(f"⛔ {sym}: news block: {guard['reason']}")
                    continue

                df = bars_df(sym, args.timeframe, 400)
                sig = make_signal(df, atr_mult=args.atr_mult)
                price = float(sig["price"])

                # manage open
                if sym in open_pos:
                    st = open_pos[sym]
                    side = st["side"]
                    best = st["best"]
                    # trailing best
                    best = max(best, price) if side=="buy" else min(best, price)
                    st["best"] = best
                    # trailing SL
                    d_atr = float(atr(df,14).iloc[-1])
                    if args.trail_mult > 0 and d_atr > 0:
                        new_sl = best - args.trail_mult*d_atr if side=="buy" else best + args.trail_mult*d_atr
                        if (side=="buy" and new_sl > st["sl"]) or (side=="sell" and new_sl < st["sl"]):
                            if args.live and modify_sl(sym, new_sl):
                                st["sl"] = new_sl

                    # partial TPs
                    part = max(round(st["lots"]/3.0, 2), 0.01)
                    if side=="buy":
                        if (not st["tp1_hit"]) and price >= st["tp1"]:
                            if args.live: market_reduce(sym, "buy", part)
                            st["tp1_hit"]=True
                        if (not st["tp2_hit"]) and price >= st["tp2"]:
                            if args.live: market_reduce(sym, "buy", part)
                            st["tp2_hit"]=True
                        if price >= st["tp3"] or price <= st["sl"]:
                            rem = max(st["lots"] - 2*part, 0.01)
                            if args.live: market_reduce(sym, "buy", rem)
                            del open_pos[sym]
                            continue
                    else:
                        if (not st["tp1_hit"]) and price <= st["tp1"]:
                            if args.live: market_reduce(sym, "sell", part)
                            st["tp1_hit"]=True
                        if (not st["tp2_hit"]) and price <= st["tp2"]:
                            if args.live: market_reduce(sym, "sell", part)
                            st["tp2_hit"]=True
                        if price <= st["tp3"] or price >= st["sl"]:
                            rem = max(st["lots"] - 2*part, 0.01)
                            if args.live: market_reduce(sym, "sell", rem)
                            del open_pos[sym]
                            continue
                    continue  # done managing

                # no open position: consider new one
                if sig["side"] in ("buy","sell"):
                    # soft bias: if opposite, skip
                    if guard["bias"] != 0:
                        want = "buy" if guard["bias"]>0 else "sell"
                        if sig["side"] != want:
                            notif.note(f"🟡 {sym}: skipped by news bias ({guard['reason']})")
                            continue

                    lots = float(args.lots)
                    sl   = float(sig["sl"])
                    if args.live:
                        rr = market_open(sym, sig["side"], lots, sl)
                        if not rr["ok"]:
                            notif.note(f"{sym} open failed: {rr}")
                            continue

                    open_pos[sym] = {
                        "side": sig["side"], "lots": lots, "entry": price, "best": price, "sl": sl,
                        "tp1": float(sig["tp1"]), "tp2": float(sig["tp2"]), "tp3": float(sig["tp3"]),
                        "tp1_hit": False, "tp2_hit": False,
                    }
                    notif.signal(sym, sig["side"].upper(), price, lots, sl, reasons=sig.get("reasons", []), quality=sig.get("score",0.7))
                    try:
                        if getattr(notif, 'enabled', False):
                            cp = None
                            try:
                                cp = charting.plot_signal_chart(sym, df, entries=[{"ts": int(df['timestamp'].iloc[-1].timestamp()*1000), "price": float(df['close'].iloc[-1]), "side": sig["side"]}], sl=sl, tps=[float(sig.get('tp1'))])
                            except Exception:
                                cp = None
                            if cp:
                                try: notif.send_photo(cp, caption=f"{sym} {sig['side'].upper()} chart (tf={args.timeframe})")
                                except Exception: pass
                    except Exception:
                        pass

            except Exception as e:
                try: notif.note(f"FX loop error {sym}: {e}")
                except Exception: pass

        # daily ping
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != last_daily:
            try: notif.note(f"Heartbeat {today}Z")
            except Exception: pass
            last_daily = today

        time.sleep(5)

if __name__ == "__main__":
    main()
