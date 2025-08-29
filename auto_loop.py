# auto_loop.py
import os, json, time
from typing import Iterator, Dict, Any
from dotenv import load_dotenv

from router import ExchangeRouter
from mt5_adapter import mt5_init, order_send_market

load_dotenv()

SIGNALS_QUEUE = os.getenv("SIGNALS_QUEUE", "runtime/signals_queue.jsonl")
SIGNALS_STATE = os.getenv("SIGNALS_STATE", "runtime/signals_offset.txt")
SLEEP_SEC     = int(os.getenv("LOOP_SLEEP_SEC", "5"))
EXECUTE       = os.getenv("ENABLE_LIVE", "false").lower() == "true"

def iter_new_signals() -> Iterator[Dict[str, Any]]:
    pos = 0
    if os.path.exists(SIGNALS_STATE):
        try:
            pos = int(open(SIGNALS_STATE, "r").read().strip() or "0")
        except:
            pos = 0
    if not os.path.exists(SIGNALS_QUEUE):
        return
    with open(SIGNALS_QUEUE, "rb") as f:
        f.seek(pos)
        for line in f:
            pos = f.tell()
            try:
                yield json.loads(line.decode("utf-8"))
            except:
                continue
    with open(SIGNALS_STATE, "w") as s:
        s.write(str(pos))

def exec_crypto(sig: Dict[str, Any]) -> Dict[str, Any]:
    r = ExchangeRouter()
    side   = sig["side"]
    symbol = sig["symbol"]
    mode   = (sig.get("mode") or r.mode).lower()

    if mode == "spot":
        qty = sig.get("qty")
        notional = sig.get("notional") or sig.get("entry")  # fallback: ~1 quote
        if not EXECUTE:
            return {"dry_run": True, "action": "spot_market", "symbol": symbol, "side": side, "notional": notional}
        return r.place_spot_market(symbol, side, qty=qty, notional=notional)
    else:
        qty = float(sig.get("qty") or 0.001)
        lev = int(sig.get("leverage") or int(os.getenv("FUT_LEVERAGE","3")))
        if not EXECUTE:
            return {"dry_run": True, "action": "futures_market", "symbol": symbol, "side": side, "qty": qty, "leverage": lev}
        return r.place_futures_market(symbol, side, qty=qty, leverage=lev)

def exec_fx(sig: Dict[str, Any]) -> Dict[str, Any]:
    mt5_init()
    lots = float(os.getenv("FX_DEFAULT_LOTS","0.01"))
    if not EXECUTE:
        return {"dry_run": True, "action": "mt5_market", "symbol": sig["symbol"], "side": sig["side"], "lots": lots}
    return order_send_market(mt5_init(), sig["symbol"], sig["side"], lots)

def main():
    print(f"[loop] start EXECUTE={EXECUTE} sleep={SLEEP_SEC}s queue={SIGNALS_QUEUE}")
    while True:
        for sig in iter_new_signals():
            try:
                venue = (sig.get("venue") or "").lower()
                if venue == "crypto":
                    res = exec_crypto(sig)
                elif venue == "fx":
                    res = exec_fx(sig)
                else:
                    res = {"ok": False, "error": f"unknown venue {venue}"}
                print({"signal": sig.get("id"), "venue": venue, "result": res})
            except Exception as e:
                print({"signal_err": str(e), "sig": sig})
        time.sleep(SLEEP_SEC)

if __name__ == "__main__":
    main()
