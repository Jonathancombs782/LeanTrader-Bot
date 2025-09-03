"""Demo runner: generate FX and crypto signals once, publish and optionally place testnet orders.
Respects ENABLE_LIVE env var; will not place real mainnet orders unless ENABLE_LIVE=true and other guards are set.
"""
from __future__ import annotations

import os
import time
from typing import List

from trader_core import TraderCore
from signals_publisher import publish_signal
from futures_signals import fut_side_from_ema
from mt5_signals import gen_signal


def _csv(s: str) -> List[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def make_fx_signal(sym: str, tf: str, core: TraderCore):
    df = core.mt5 and core.mt5  # placeholder to show mt5 is initialized
    try:
        df = __import__("mt5_signals").mt5_signals.fetch_bars_safe(sym, tf, limit=250)
    except Exception:
        try:
            from mt5_signals import fetch_bars_safe

            df = fetch_bars_safe(sym, tf, limit=250)
        except Exception:
            return None
    if df is None or getattr(df, "empty", True):
        return None
    sig = gen_signal(df)
    if not sig:
        return None
    entry = float(df["close"].iloc[-1])
    return {
        "market": "FX",
        "symbol": sym,
        "tf": tf,
        "side": sig["side"],
        "entry": entry,
        "tp1": sig.get("tp", entry * 1.001),
        "tp2": sig.get("tp", entry * 1.002),
        "tp3": sig.get("tp", entry * 1.003),
        "sl": sig.get("sl", entry * 0.998),
        "confidence": float(sig.get("conf", 0.6)),
        "context": ["demo_run", "mt5"] ,
    }


def make_crypto_signal(sym: str, tf: str, core: TraderCore):
    try:
        m = core.router._resolve_symbol(sym, futures=False)
        rows = core.router.safe_fetch_ohlcv(m, timeframe=tf, limit=150)
        import pandas as pd

        if not rows:
            return None
        df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
        df["time"] = pd.to_datetime(df["time"], unit="ms")
    except Exception:
        return None
    side = fut_side_from_ema(df)
    if not side:
        return None
    entry = float(df["close"].iloc[-1])
    return {
        "market": "crypto",
        "symbol": sym,
        "tf": tf,
        "side": side,
        "entry": entry,
        "tp1": entry * (1.001 if side == "buy" else 0.999),
        "tp2": entry * (1.002 if side == "buy" else 0.998),
        "tp3": entry * (1.005 if side == "buy" else 0.995),
        "sl": entry * (0.997 if side == "buy" else 1.003),
        "confidence": 0.6,
        "context": ["demo_run", "ccxt"],
    }


def main():
    enable_live = os.getenv("ENABLE_LIVE", "false").lower() in ("1", "true", "yes")
    fx_syms = _csv(os.getenv("FX_SYMBOLS", "EURUSD,GBPUSD"))
    fx_tfs = _csv(os.getenv("FX_TFS", "M5,M15"))
    crypto_syms = _csv(os.getenv("CRYPTO_SYMBOLS", "BTC/USDT,ETH/USDT"))
    crypto_tfs = _csv(os.getenv("CRYPTO_SPOT_TFS", "1m,5m"))

    core = TraderCore(fx_syms, fx_tfs, crypto_syms, crypto_tfs, [], [], loop_sec=1)
    # short pause to ensure router/mt5 initialized
    time.sleep(1)

    published = []
    # FX
    for s in fx_syms:
        for tf in fx_tfs:
            sig = make_fx_signal(s, tf, core)
            if sig:
                res = publish_signal(sig)
                print("published fx", s, tf, res)
                published.append((sig, res))
    # Crypto
    for s in crypto_syms:
        for tf in crypto_tfs:
            sig = make_crypto_signal(s, tf, core)
            if sig:
                res = publish_signal(sig)
                print("published crypto", s, tf, res)
                published.append((sig, res))

    # Attempt testnet orders only if ENABLE_LIVE explicitly true
    if enable_live:
        print("ENABLE_LIVE=true -> attempting to place testnet orders for published signals")
        for sig, _ in published:
            try:
                if sig["market"].lower() == "crypto":
                    # place via router (uses internal testnet/paper flags)
                    out = core.router.place_spot_market(sig["symbol"], sig["side"], notional=5.0)
                    print("order result:", out)
                else:
                    # for FX, place via MT5 demo
                    out = core.mt5 and __import__("mt5_signals").mt5_signals.place_mt5_signal(core.mt5, sig["symbol"], sig["side"], 0.01, sig["sl"], sig["tp1"])
                    print("mt5 order:", out)
            except Exception as e:
                print("order error:", e)
    else:
        print("ENABLE_LIVE not true; skipping order placement (dry-run demo only)")


if __name__ == "__main__":
    main()
