"""Run a single safe polling loop of TraderCore (no continuous loop).
This runner respects ENABLE_LIVE and will not place live orders unless ENABLE_LIVE=true
"""
from __future__ import annotations

import os
from trader_core import TraderCore


def main():
    fx = [s for s in os.getenv("FX_SYMBOLS", "XAUUSD,EURUSD,USDJPY").split(",") if s]
    fxt = [s for s in os.getenv("FX_TFS", "M5,M15").split(",") if s]
    sp = [s for s in os.getenv("CRYPTO_SYMBOLS", "BTC/USDT,DOGE/USDT").split(",") if s]
    spt = [s for s in os.getenv("CRYPTO_SPOT_TFS", "1m,5m").split(",") if s]
    fu = [s for s in os.getenv("CRYPTO_FUTURES", "BTC/USDT,ETH/USDT").split(",") if s]
    fut = [s for s in os.getenv("CRYPTO_FUT_TFS", "1m,5m").split(",") if s]

    core = TraderCore(fx, fxt, sp, spt, fu, fut, loop_sec=1)
    # Run each poller once
    print("Running single-run trader (safe) ...")
    if fx:
        core._poll_fx()
    if sp:
        core._poll_crypto_spot()
    if fu:
        core._poll_crypto_futures()


if __name__ == "__main__":
    main()
