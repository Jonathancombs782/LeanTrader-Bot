from __future__ import annotations

import argparse
import json
import os
from typing import Any

from dex_router import execute_swap


def main() -> int:
    p = argparse.ArgumentParser(description="Demo DEX swap using guarded router")
    p.add_argument("--symbol", default=os.getenv("DEX_SYMBOL", "ETH/USDC"))
    p.add_argument("--timeframe", default=os.getenv("DEX_TIMEFRAME", "M1"))
    p.add_argument("--notional", type=float, default=float(os.getenv("DEX_NOTIONAL", "250000")))
    p.add_argument("--slip", type=int, default=int(os.getenv("DEX_MAX_SLIPPAGE_BPS", "30")))
    p.add_argument("--risk", default=os.getenv("MEMPOOL_RISK_PATH", "runtime/mempool_risk.json"))
    args = p.parse_args()

    # Dummy tx builder and senders (replace with real encoder and submitters)
    def tx_builder(slippage_bps: int) -> Any:
        return {"slippage_bps": slippage_bps, "symbol": args.symbol}

    def send_public(tx: Any) -> Any:
        # demo: pretend failure to trigger private path when risk high/size large
        return None

    def send_private(tx: Any) -> Any:
        return {"ok": True, "txid": "0xdeadbeef"}

    res = execute_swap(
        asset=args.symbol,
        timeframe=args.timeframe,
        notional_usd=args.notional,
        max_slippage_bps=args.slip,
        tx_builder=tx_builder,
        send_public=send_public,
        private_sender=send_private,
        risk_json_path=args.risk,
    )
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

