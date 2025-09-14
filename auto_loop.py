# auto_loop.py
import json
import os
import time
from typing import Any, Dict, Iterator

from dotenv import load_dotenv

from router import ExchangeRouter  # noqa: E402

# Avoid top-level import of mt5_adapter which can raise in environments
# without MetaTrader5. Import lazily inside fx executor.


load_dotenv()

SIGNALS_QUEUE = os.getenv("SIGNALS_QUEUE", "runtime/signals_queue.jsonl")
SIGNALS_STATE = os.getenv("SIGNALS_STATE", "runtime/signals_offset.txt")
SLEEP_SEC = int(os.getenv("LOOP_SLEEP_SEC", "5"))
EXECUTE = os.getenv("ENABLE_LIVE", "false").lower() == "true"


def iter_new_signals() -> Iterator[Dict[str, Any]]:
    pos = 0
    if os.path.exists(SIGNALS_STATE):
        try:
            pos = int(open(SIGNALS_STATE, "r").read().strip() or "0")
        except Exception:
            pos = 0
    if not os.path.exists(SIGNALS_QUEUE):
        return
    with open(SIGNALS_QUEUE, "rb") as f:
        f.seek(pos)
        for line in f:
            pos = f.tell()
            try:
                yield json.loads(line.decode("utf-8"))
            except Exception:
                continue
    with open(SIGNALS_STATE, "w") as s:
        s.write(str(pos))


def exec_crypto(sig: Dict[str, Any]) -> Dict[str, Any]:
    r = ExchangeRouter()
    side = sig["side"]
    symbol = sig["symbol"]
    mode = (sig.get("mode") or r.mode).lower()

    if mode == "spot":
        qty = sig.get("qty")
        notional = sig.get("notional") or sig.get("entry")  # fallback: ~1 quote
        if not EXECUTE:
            return {
                "dry_run": True,
                "action": "spot_market",
                "symbol": symbol,
                "side": side,
                "notional": notional,
            }
        return r.place_spot_market(symbol, side, qty=qty, notional=notional)
    else:
        qty = float(sig.get("qty") or 0.001)
        lev = int(sig.get("leverage") or int(os.getenv("FUT_LEVERAGE", "3")))
        if not EXECUTE:
            return {
                "dry_run": True,
                "action": "futures_market",
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "leverage": lev,
            }
        return r.place_futures_market(symbol, side, qty=qty, leverage=lev)


def _import_mt5_helpers():
    try:
        import importlib

        mod = importlib.import_module("mt5_adapter")
        return getattr(mod, "mt5_init", lambda: None), getattr(
            mod, "order_send_market", lambda *a, **k: {"ok": False, "comment": "mt5 unavailable"}
        )
    except Exception:
        try:
            import importlib.util
            import sys
            from pathlib import Path

            repo_root = Path(__file__).resolve().parent
            candidate = repo_root / "mt5_adapter.py"
            if candidate.exists():
                spec = importlib.util.spec_from_file_location("mt5_adapter", str(candidate))
                mod = importlib.util.module_from_spec(spec)
                sys.modules["mt5_adapter"] = mod
                spec.loader.exec_module(mod)  # type: ignore
                return getattr(mod, "mt5_init", lambda: None), getattr(
                    mod, "order_send_market", lambda *a, **k: {"ok": False, "comment": "mt5 unavailable"}
                )
        except Exception:
            pass

    def mt5_init():
        return None

    def order_send_market(mt5mod, symbol, side, lots, sl=None, tp=None, deviation=20):
        return {"ok": False, "comment": "mt5 unavailable"}

    return mt5_init, order_send_market


def exec_fx(sig: Dict[str, Any]) -> Dict[str, Any]:
    # lazy import to avoid import-time failure when mt5_adapter isn't present
    mt5_init, order_send_market = _import_mt5_helpers()

    # initialize mt5 context (noop for shim)
    mt5ctx = mt5_init()
    lots = float(os.getenv("FX_DEFAULT_LOTS", "0.01"))
    if not EXECUTE:
        return {
            "dry_run": True,
            "action": "mt5_market",
            "symbol": sig["symbol"],
            "side": sig["side"],
            "lots": lots,
        }

    # perform real order via adapter
    return order_send_market(mt5ctx, sig["symbol"], sig["side"], lots)


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
