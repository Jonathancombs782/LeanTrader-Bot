from __future__ import annotations

import json
import sys
import time
from typing import Any, Dict


def jlog(level: str, svc: str, event: str, **fields: Any) -> None:
    rec: Dict[str, Any] = {
        "ts": int(time.time()),
        "level": str(level).lower(),
        "svc": svc,
        "event": event,
    }
    rec.update(fields)
    try:
        sys.stdout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    except Exception:
        # last resort
        print(f"[{svc}] {event} {fields}")

