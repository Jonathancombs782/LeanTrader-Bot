from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

from core.events.web3_consumer import subscribe


def main() -> int:
    p = argparse.ArgumentParser(description="On-chain fuser: ingest events and write ONCHAIN_EVENTS_PATH periodically")
    p.add_argument("--channel", default=os.getenv("ONCHAIN_CHANNEL", "signal.web3.trending"))
    p.add_argument("--redis", default=os.getenv("REDIS_URL", ""))
    p.add_argument("--out", default=os.getenv("ONCHAIN_EVENTS_PATH", "runtime/onchain_events.json"))
    p.add_argument("--max-events", type=int, default=int(os.getenv("ONCHAIN_MAX_EVENTS", "2000")))
    p.add_argument("--flush-every", type=int, default=int(os.getenv("ONCHAIN_FLUSH_SEC", "30")))
    args = p.parse_args()

    buf: List[Dict[str, Any]] = []
    last_flush = 0.0
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def _cb(evt: Dict[str, Any]) -> None:
        nonlocal buf, last_flush
        try:
            if not isinstance(evt, dict):
                return
            # Normalize to detectors' shape when possible
            typ = str(evt.get("type") or evt.get("event") or "").lower()
            if not typ:
                return
            evt["type"] = typ
            buf.append(evt)
            if len(buf) > max(100, args.max_events):
                buf = buf[-args.max_events :]
        except Exception:
            return

        now = time.time()
        if now - last_flush >= max(5, args.flush_every):
            try:
                out_path.write_text(json.dumps(buf, ensure_ascii=False), encoding="utf-8")
                last_flush = now
            except Exception:
                pass

    subscribe(_cb, channel=args.channel, redis_url=args.redis or None)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

