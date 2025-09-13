from __future__ import annotations

import argparse
import os
import time
from prometheus_client import start_http_server  # type: ignore


def main() -> int:
    p = argparse.ArgumentParser(description="Start Prometheus HTTP metrics exporter")
    p.add_argument("--port", type=int, default=int(os.getenv("METRICS_PORT", "9000")))
    p.add_argument("--addr", default=os.getenv("METRICS_ADDR", "0.0.0.0"))
    args = p.parse_args()

    start_http_server(args.port, addr=args.addr)
    print(f"metrics exporter listening on {args.addr}:{args.port}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

