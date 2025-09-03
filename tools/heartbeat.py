"""Write a heartbeat file every 30s to indicate supervisor health.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

RUNTIME = Path(__file__).resolve().parent.parent / "runtime"
HB = RUNTIME / "heartbeat.json"
RUNTIME.mkdir(parents=True, exist_ok=True)


def main(interval: int = 30):
    while True:
        now = int(time.time())
        data = {"ts": now, "status": "ok"}
        try:
            HB.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass
        time.sleep(interval)


if __name__ == "__main__":
    main()
