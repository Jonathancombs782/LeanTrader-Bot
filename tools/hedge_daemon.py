from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

from hedging.multi_account import NET_EXPOSURE_USD, account_state, execute_hedge, hedge_plan, net_exposure, Instrument


def _load_instruments(path: str) -> Dict[str, List[Instrument]]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        out: Dict[str, List[Instrument]] = {}
        for asset, arr in (data or {}).items():
            lst = []
            for it in (arr or []):
                try:
                    lst.append(Instrument(asset=asset.upper(), symbol=str(it["symbol"]), kind=str(it.get("kind", "futures")), vol=float(it.get("vol", 0.02))))
                except Exception:
                    continue
            out[asset.upper()] = lst
        return out
    except Exception:
        return {}


def main() -> int:
    p = argparse.ArgumentParser(description="Hedge daemon: compute net exposure and place hedges")
    p.add_argument("--instruments", default=os.getenv("HEDGE_INSTRUMENTS", "runtime/hedge_instruments.json"))
    p.add_argument("--execute", action="store_true", help="execute hedges (live)")
    p.add_argument("--interval", type=int, default=int(os.getenv("HEDGE_INTERVAL_SEC", "3600")))
    args = p.parse_args()

    # Build venues list (support multiple via HEDGE_VENUES=paper,bybit,...)
    venues: List[Any] = []
    hedge_venues = [s.strip().lower() for s in os.getenv("HEDGE_VENUES", "").split(",") if s.strip()]
    try:
        from traders_core.router import ExchangeRouter  # type: ignore
        import copy

        if not hedge_venues:
            venues.append(ExchangeRouter())
        else:
            orig_id = os.getenv("EXCHANGE_ID", "")
            for vid in hedge_venues:
                os.environ["EXCHANGE_ID"] = vid
                try:
                    venues.append(ExchangeRouter())
                except Exception:
                    continue
            if orig_id:
                os.environ["EXCHANGE_ID"] = orig_id
    except Exception:
        pass

    inst_map = _load_instruments(args.instruments)
    if not inst_map:
        # default mapping for majors
        inst_map = {
            "BTC": [Instrument(asset="BTC", symbol="BTC/USDT:USDT", kind="futures", vol=0.03)],
            "ETH": [Instrument(asset="ETH", symbol="ETH/USDT:USDT", kind="futures", vol=0.035)],
        }

    while True:
        try:
            expo = net_exposure(venues)
            # Greeks-aware plan when enabled
            if os.getenv("HEDGE_GREEKS", "false").strip().lower() in ("1", "true", "yes", "on"):
                try:
                    from hedging.multi_account import hedge_plan_greeks  # type: ignore

                    plan = hedge_plan_greeks(expo, inst_map)
                except Exception:
                    plan = hedge_plan(expo, inst_map)
            else:
                plan = hedge_plan(expo, inst_map)
            if args.execute or os.getenv("HEDGE_LIVE", "false").lower() == "true":
                execute_hedge(plan)
            # dump snapshot
            Path("runtime/net_exposure.json").write_text(json.dumps(expo, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        time.sleep(max(60, int(args.interval)))


if __name__ == "__main__":
    raise SystemExit(main())
