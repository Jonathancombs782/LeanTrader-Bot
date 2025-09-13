from __future__ import annotations

import json
import os
import urllib.request


def notify(text: str) -> bool:
    url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not url:
        return False
    try:
        body = json.dumps({"text": str(text)}).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as _:
            return True
    except Exception:
        return False


def warn(title: str, reasons: list[str] | None = None) -> bool:
    msg = f":warning: {title}"
    if reasons:
        msg += "\n- " + "\n- ".join([str(r) for r in reasons])
    return notify(msg)


__all__ = ["notify", "warn"]
