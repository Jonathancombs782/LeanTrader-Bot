# auto_loop.py
import os, time
from pprint import pprint
from typing import Dict, Any
from router import ExchangeRouter
from strategist import breakout_signal
from memory import Memory

def pct(a: float, b: float) -> float:
    return (a-b)/b if b else 0.0

def main() -> None:
    r  = ExchangeRouter()
    mem = Memory()

    # env knobs
    quote     = os.getenv("CRYPTO_SCAN_QUOTE", "USDT")
    topn      = int(os.getenv("CRYPTO_SCAN_TOPN", "12"))
    limit     = int(os.getenv("CRYPTO_OHLCV_LIMIT", "120"))
    sleep_s   = int(os.getenv("LOOP_SLEEP", "30"))
    max_pos   = int(os.getenv("MAX_OPEN_POS", "3"))
    # spot sizing
    stake_usd = float(os.getenv("STAKE_USD", "5"))
    tp_spot   = float(os.getenv("CRYPTO_TP_PCT", "0.002"))   # +0.2%
    sl_spot   = float(os.getenv("CRYPTO_SL_PCT", "0.001"))   # -0.1%
    # futures sizing
    fut_qty   = float(os.getenv("CRYPTO_FUT_QTY", "0.001"))
    lev       = int(os.getenv("FUT_LEVERAGE", "3"))
    tp_fut    = float(os.getenv("FUT_TP_PCT", "0.003"))
    sl_fut    = float(os.getenv("FUT_SL_PCT", "0.0015"))

    print("router:", r.info())

    while True:
        try:
            # 1) scan
            movers = r.scan_top_movers(topn=topn, quote=quote, limit=limit)

            # 2) enter signals (if capacity)
            for m in movers:
                if len(mem.open_positions()) >= max_pos: break
                # prefer safe wrapper and guard errors
                try:
                    if hasattr(r, 'safe_fetch_ohlcv'):
                        try:
                            bars = r.safe_fetch_ohlcv(m["symbol"], timeframe="1m", limit=limit)
                        except Exception as e:
                            print(f"[traders_core.auto_loop] safe_fetch_ohlcv failed for {m['symbol']}: {e}")
                            bars = []
                    else:
                        try:
                            bars = r.fetch_ohlcv(m["symbol"], timeframe="1m", limit=limit)
                        except Exception as e:
                            print(f"[traders_core.auto_loop] fetch_ohlcv failed for {m['symbol']}: {e}")
                            bars = []
                except Exception as e:
                    print(f"[traders_core.auto_loop] unexpected error fetching {m['symbol']}: {e}")
                    bars = []
                sig  = breakout_signal(bars)
                if sig["side"] != "buy": continue
                entry = float(sig["entry"])
                if r.mode == "spot":
                    res = r.place_spot_market(m["symbol"], "buy", notional=stake_usd)
                    if not res.get("ok"): 
                        print("[spot order error]", res); 
                        continue
                    qty = float(res["result"].get("amount", res["result"].get("filled", 0)))
                    mem.add_position({
                        "symbol": m["symbol"], "side": "long", "mode": "spot",
                        "px_open": entry, "qty": qty, "tp_pct": tp_spot, "sl_pct": sl_spot
                    })
                else:  # linear
                    res = r.place_futures_market(m["symbol"], "buy", qty=fut_qty, leverage=lev)
                    if not res.get("ok"): 
                        print("[fut order error]", res); 
                        continue
                    mem.add_position({
                        "symbol": m["symbol"], "side": "long", "mode": "futures",
                        "px_open": entry, "qty": fut_qty, "tp_pct": tp_fut, "sl_pct": sl_fut, "lev": lev
                    })

            # 3) manage exits
            for p in list(mem.open_positions()):
                px = r.last_price(p["symbol"])
                up =  pct(px, p["px_open"])
                tp =  p["tp_pct"]; sl = p["sl_pct"]
                hit_tp = up >= tp
                hit_sl = up <= -sl

                if hit_tp or hit_sl:
                    if p["mode"] == "spot":
                        # sell same qty
                        r.place_spot_market(p["symbol"], "sell", qty=p["qty"])
                    else:
                        # reduce-only close
                        r.place_futures_market(p["symbol"], "sell", qty=p["qty"], leverage=p.get("lev", 1), close=True)
                    pnl = (px - p["px_open"]) * p["qty"]
                    mem.close_position(p["id"], px_close=px, reason=("TP" if hit_tp else "SL"), pnl=pnl)

            # 4) heartbeat
            print(f"[loop] open={len(mem.open_positions())} | scan={len(movers)}"); time.sleep(sleep_s)

        except Exception as e:
            print("[loop error]", e); time.sleep(sleep_s)

if __name__ == "__main__":
    main()
