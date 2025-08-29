# auto_pilot.py
from __future__ import annotations
import os, time, json
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

import pandas as pd

from dotenv import load_dotenv
load_dotenv()

from router import ExchangeRouter            # your renamed router
from brain import Brain, Memory, VolSizer, Guards

def to_df(ohlcv: List[List[float]]) -> pd.DataFrame:
    if not ohlcv: return pd.DataFrame()
    df = pd.DataFrame(ohlcv, columns=["time","open","high","low","close","volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    return df

def fetch_df(r: ExchangeRouter, symbol: str, tf: str, limit: int = 240) -> pd.DataFrame:
    try:
        o = r.safe_fetch_ohlcv(symbol, timeframe=tf, limit=limit)
        return to_df(o)
    except Exception as e:
        print(f"[data] {symbol} {tf} error: {e}")
        return pd.DataFrame()

def account_balance_usd(r: ExchangeRouter) -> float:
    try:
        acc = r.account()
        if acc.get("mode") == "paper":
            return float(acc.get("paper_cash", 0))
        bal = r.safe_fetch_balance() if hasattr(r, "safe_fetch_balance") else {}
        usdt = bal.get("free", {}).get("USDT") or bal.get("USDT", 0)
        return float(usdt or 0)
    except Exception:
        return 0.0

def main() -> None:
    r = ExchangeRouter()
    b = Brain()
    mem = Memory()
    guards = Guards(mem)

    tf = os.getenv("BRAIN_TF", "1m")
    mode = r.mode
    print(f"router={{'paper': {r.paper}, 'testnet': {r.testnet}, 'mode': '{mode}', 'live': {r.live}}}")

    # choose symbols (USDT majors)
    symbols = ["BTC/USDT","ETH/USDT","SOL/USDT","XRP/USDT","DOGE/USDT"]
    print("scan:", symbols)

    state: Dict[str, Dict[str, Any]] = {}  # symbol -> {side, entry, qty/notional}
    while True:
        ok, why = guards.day_ok()
        if not ok:
            print(f"[halt] {why}")
            time.sleep(60); continue

        bal = account_balance_usd(r)
        sizer = VolSizer(bal)

        for sym in symbols:
            df = fetch_df(r, sym, tf, limit=240)
            if len(df) < 60: 
                print(f"[skip] {sym} no bars")
                continue

            adv = b.decide(sym, df)
            if adv.side is None:
                continue

            stake_usd = sizer.usd(df)
            sess_mult = 1.0
            price = float(df["close"].iloc[-1])

            # funding guard for futures
            if r.mode != "spot":
                f = None
                try:
                    if hasattr(r.ex, "fetch_funding_rate"):
                        fr = r.ex.fetch_funding_rate(sym)
                        f = float(fr.get("fundingRate", 0)) if isinstance(fr, dict) else None
                except Exception:
                    f = None
                okf, whyf = guards.funding_ok(f)
                if not okf:
                    print(f"[guard] {sym} {whyf}")
                    continue

            # manage existing trade
            st = state.get(sym)
            if st:
                new_sl, new_tp = b.trail(st["side"], st["entry"], df)
                st["sl"], st["tp"] = new_sl, new_tp
                # simple exit rules on spot (simulate) or futures (reduceOnly)
                if st["side"] == "buy":
                    if price <= st["sl"] or price >= st["tp"]:
                        res = _close(r, sym, st, price)
                        mem.push_trade(sym, "buy", res.get("pnl", 0.0))
                        state.pop(sym, None)
                else:
                    if price >= st["sl"] or price <= st["tp"]:
                        res = _close(r, sym, st, price)
                        mem.push_trade(sym, "sell", res.get("pnl", 0.0))
                        state.pop(sym, None)
                continue  # do not open new one immediately

            # open a new trade
            side = adv.side
            if r.mode == "spot":
                notional = stake_usd
                res = r.place_spot_market(sym, side, notional=notional)
                ok = res.get("ok")
                if ok:
                    state[sym] = {"side": side, "entry": price, "sl": adv.sl, "tp": adv.tp, "notional": notional}
                    print(f"[open] spot {sym} {side} ${notional:.2f} @ {price:.4f} | {adv.reason}")
                else:
                    print(f"[fail] spot {sym} {res}")
            else:
                # linear USDT-perp: qty in base coin
                qty = max(0.0001, stake_usd / price)
                lev = int(float(os.getenv("FUT_LEVERAGE", "3")))
                res = r.place_futures_market(sym, side, qty=qty, leverage=lev)
                ok = res.get("ok")
                if ok:
                    state[sym] = {"side": side, "entry": price, "sl": adv.sl, "tp": adv.tp, "qty": qty}
                    print(f"[open] fut {sym} {side} {qty:.6f} @ {price:.4f} x{lev} | {adv.reason}")
                else:
                    print(f"[fail] fut {sym} {res}")

        time.sleep(20)

def _close(r: ExchangeRouter, sym: str, st: Dict[str,Any], price_now: float) -> Dict[str,Any]:
    side = st["side"]
    entry = st["entry"]
    pnl = (price_now - entry) if side == "buy" else (entry - price_now)
    if r.mode == "spot":
        # simulate: opposite side notional
        notional = st["notional"]
        res = r.place_spot_market(sym, "sell" if side == "buy" else "buy", notional=notional)
    else:
        qty = st["qty"]
        res = r.place_futures_market(sym, "sell" if side == "buy" else "buy", qty=qty, close=True)
    res["pnl"] = float(pnl)
    print(f"[close] {sym} {side} pnl≈{pnl:.4f} @ {price_now:.4f}")
    return res

if __name__ == "__main__":
    main()
