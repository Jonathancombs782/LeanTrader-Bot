# crypto_trader.py
from __future__ import annotations
import argparse, os, math, time
from typing import Dict, Any, List
import numpy as np

from router import ExchangeRouter

def ema(x: np.ndarray, n: int) -> np.ndarray:
    k = 2.0/(n+1.0)
    out = np.empty_like(x, dtype=float)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = out[i-1] + k*(x[i]-out[i-1])
    return out

def momentum_signal(closes: List[float]) -> str:
    c = np.array(closes, dtype=float)
    e12 = ema(c, 12)
    e26 = ema(c, 26)
    if e12[-1] > e26[-1] and c[-1] > e12[-1]:
        return "buy"
    if e12[-1] < e26[-1] and c[-1] < e12[-1]:
        return "sell"
    return "flat"

def _close_list(ohlcv) -> List[float]:
    return [float(r[4]) for r in ohlcv]

def trade_once(r: ExchangeRouter, *, prefer_futures: bool, notional_spot: float = 5.0) -> Dict[str, Any]:
    syms = r.list_scan_symbols()
    if not syms:
        return {"ok": False, "error": "no symbols to scan"}

    chosen = syms[0]  # top mover
    # router may expose fetch_ohlcv (safe) which returns list of bars
    try:
        # Always prefer the router's safe wrapper which synthesizes fallbacks when needed
        ohlcv = r.safe_fetch_ohlcv(chosen, timeframe="1m", limit=r.ohlcv_limit)
    except Exception as e:
        # If even the safe wrapper errors, log and continue with empty bars to avoid crashing
        print(f"[crypto_trader] safe_fetch_ohlcv failed for {chosen}: {e}")
        ohlcv = []
    closes = _close_list(ohlcv)
    sig = momentum_signal(closes)

    print(f"[scan] top={chosen} sig={sig} last={closes[-1]:.6f}")

    if sig == "flat":
        return {"ok": True, "note": "no action"}

    if prefer_futures:
        linear = chosen.replace("/USDT", "/USDT:USDT") if ":USDT" not in chosen else chosen
        side = "buy" if sig == "buy" else "sell"
        res = r.place_futures_market(linear, side, qty=None, leverage=None)
        # ensure consistent dict shape
        if isinstance(res, dict) and res.get("ok") is True:
            return {"ok": True, "mode": "futures", "order": res.get("result")}
        return {"ok": True, "mode": "futures", "order": res}
    else:
        if sig == "buy":
            res = r.place_spot_market(chosen, "buy", notional=notional_spot)
            if isinstance(res, dict) and res.get("ok"):
                return {"ok": True, "mode": "spot", "order": res.get("result")}
            return {"ok": True, "mode": "spot", "order": res}
        else:
            # For a real sell/exit you must have base coin; in demo we try small qty
            res = r.place_spot_market(chosen, "sell", qty=0.0002)
            if isinstance(res, dict) and res.get("ok"):
                return {"ok": True, "mode": "spot", "order": res.get("result")}
            return {"ok": True, "mode": "spot", "order": res}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefer", choices=["spot","futures"], default=os.getenv("EXCHANGE_MODE","spot"))
    ap.add_argument("--notional", type=float, default=5.0, help="spot buy notional (USDT)")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--sleep", type=int, default=60)
    args = ap.parse_args()

    r = ExchangeRouter()
    print(f"router ready | paper={r.paper} | mode={args.prefer}")

    while True:
        try:
            out = trade_once(r, prefer_futures=(args.prefer=="futures"), notional_spot=args.notional)
            print(out)
        except Exception as e:
            print("error:", e)
        if not args.loop:
            break
        time.sleep(args.sleep)

if __name__ == "__main__":
    main()
