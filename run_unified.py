# run_unified.py
from __future__ import annotations

import argparse

from trader_core import TraderCore
from traders_core.services.web3_bias_daemon import start as start_bias
from traders_core.services.pnl_daemon import start as start_pnl
try:
    from traders_core.services.ratio_arb_daemon import start as start_ratio_arb
except Exception:
    start_ratio_arb = None


def main():
    ap = argparse.ArgumentParser()
    import os

    ap.add_argument("--fx", default=os.getenv("FX_SYMBOLS", "XAUUSD,EURUSD,USDJPY"))
    ap.add_argument("--fx_tfs", default=os.getenv("FX_TFS", "M5,M15"))
    ap.add_argument("--spot", default=os.getenv("CRYPTO_SYMBOLS", "BTC/USDT,DOGE/USDT"))
    ap.add_argument("--spot_tfs", default=os.getenv("CRYPTO_SPOT_TFS", "1m,5m"))
    ap.add_argument("--fut", default=os.getenv("CRYPTO_FUTURES", "BTC/USDT,ETH/USDT"))
    ap.add_argument("--fut_tfs", default=os.getenv("CRYPTO_FUT_TFS", "1m,5m"))
    ap.add_argument("--loop", type=int, default=20)
    ap.add_argument("--atr_th", type=float, default=0.003)
    ap.add_argument("--bbw_th", type=float, default=0.02)
    args = ap.parse_args()

    fx = [s for s in args.fx.split(",") if s]
    fxt = [s for s in args.fx_tfs.split(",") if s]
    sp = [s for s in args.spot.split(",") if s]
    spt = [s for s in args.spot_tfs.split(",") if s]
    fu = [s for s in args.fut.split(",") if s]
    fut = [s for s in args.fut_tfs.split(",") if s]

    # Start background services (lightweight)
    try:
        import os
        run_daemons = os.getenv("RUN_DAEMONS", "true").strip().lower() in ("1", "true", "yes", "on")
        if run_daemons:
            start_bias()
            start_pnl()
            if os.getenv("RUN_RATIO_ARB", "false").lower() == "true" and start_ratio_arb:
                start_ratio_arb()
    except Exception:
        pass

    core = TraderCore(
        fx,
        fxt,
        sp,
        spt,
        fu,
        fut,
        loop_sec=args.loop,
        atr_th=args.atr_th,
        bbw_th=args.bbw_th,
    )
    core.run_forever()


if __name__ == "__main__":
    main()
