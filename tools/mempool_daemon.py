from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

from core.events.web3_consumer import subscribe
from w3guard.guards import MempoolMonitor, get_mempool_tuning, MEMPOOL_RISK, load_mempool_tuning_from_file


def main() -> int:
    p = argparse.ArgumentParser(description="Mempool monitor daemon: updates MEMPOOL_RISK gauge")
    p.add_argument("--symbol", default=os.getenv("MEMPOOL_SYMBOL", "ETH/USDC"))
    p.add_argument("--timeframe", default=os.getenv("MEMPOOL_TIMEFRAME", "M1"))
    p.add_argument("--channel", default=os.getenv("MEMPOOL_CHANNEL", "signal.web3.pending"))
    p.add_argument("--redis", default=os.getenv("REDIS_URL", ""))
    p.add_argument("--write-json", default=os.getenv("MEMPOOL_RISK_PATH", "runtime/mempool_risk.json"))
    args = p.parse_args()

    # Optional tuning file
    try:
        cfg_file = os.getenv("MEMPOOL_TUNING_FILE", "mempool_tuning.yml").strip()
        if cfg_file and os.path.exists(cfg_file):
            load_mempool_tuning_from_file(cfg_file)
    except Exception:
        pass
    tune = get_mempool_tuning(args.symbol, args.timeframe)
    mon = MempoolMonitor(symbol=args.symbol, timeframe=args.timeframe, window_ms=tune["window_ms"], drop_bps=tune["drop_bps"]) 

    out_path = Path(args.write_json).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def _cb(tx: Dict[str, Any]) -> None:
        ev = mon.observe(tx)
        try:
            MEMPOOL_RISK.labels(symbol=args.symbol.upper(), timeframe=args.timeframe.upper()).set(mon.current_risk)
        except Exception:
            pass
        try:
            out = {"ts": int(time.time()), "symbol": args.symbol, "timeframe": args.timeframe, "risk": mon.current_risk, "last_event": ev}
            out_path.write_text(json.dumps(out), encoding="utf-8")
        except Exception:
            pass

    subscribe(_cb, channel=args.channel, redis_url=args.redis or None)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
